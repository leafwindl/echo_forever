import json
import logging
import re
from datetime import UTC, datetime

from shared.config import settings
from shared.prompting.renderer import (
    PERSONA_ANCHOR_POLICY,
    estimate_prompt_tokens,
    render_proactive_context,
    render_prompt_layers,
)

from features.assistant_persona.public import get_assistant_persona
from features.chat.domain.dialogue_style import (
    should_pause_followup_questions,
    should_suppress_repeated_greeting,
)
from features.chat.domain.entities import ChatContext
from features.chat.domain.temporal_context import build_temporal_context, format_gap_seconds
from features.chat.infrastructure import postgres_repositories
from features.memory.public import (
    list_memories,
    list_memory_embedding_records,
    retrieve_relevant_memories,
)
from features.persona.public import get_persona
from features.relationship.public import get_relationship_context
from features.user_profile.public import evaluate_profile_onboarding, get_user_profile

logger = logging.getLogger(__name__)

MAX_LONG_TERM_MEMORIES = 8


def _trim_history_by_tokens(history: list[dict], max_tokens: int) -> list[dict]:
    """从旧到新丢，保留最近的消息；至少留一条，避免上下文全空。"""
    if max_tokens <= 0:
        return history
    total = 0
    kept: list[dict] = []
    for message in reversed(history):
        content = str(message.get("content") or "")
        cost = estimate_prompt_tokens(content) + 4
        if kept and total + cost > max_tokens:
            break
        kept.append(message)
        total += cost
    kept.reverse()
    return kept




_MESSAGE_TIME_PREFIX = re.compile(
    r"^\s*[\[［]\s*消息时间[^\]］\r\n]*[\]］]\s*(?:\r?\n)?"
)
_SESSION_BOUNDARY_LINE = re.compile(
    r"^\s*[\[［]\s*会话时间边界[\]］][^\r\n]*(?:\r?\n)?",
    flags=re.MULTILINE,
)
_ATTACHMENT_BLOCK = re.compile(
    r"\s*\n?\[本条消息的可信结构化附件\][\s\S]*$",
)


def _list_active_memories_for_context(user_id: str) -> list[dict[str, object]]:
    result = list_memories(user_id=user_id, memory_status="active", limit=MAX_LONG_TERM_MEMORIES)
    return [
        {
            "memory_id": memory.memory_id,
            "memory_type": memory.memory_type,
            "content": memory.content,
            "importance": memory.importance.value,
            "updated_at": memory.updated_at,
        }
        for memory in result.memories
    ]


async def _load_long_term_memories(
    user_id: str,
    user_message: str,
) -> tuple[list[dict[str, object]], str]:
    has_vector_records = bool(
        list_memory_embedding_records(user_id, embedding_model=settings.embedding_model)
    )
    try:
        relevant_memories = await retrieve_relevant_memories(
            user_id=user_id,
            query=user_message,
            top_k=settings.memory_vector_top_k,
            score_threshold=settings.memory_vector_score_threshold,
        )
    except Exception as exc:
        logger.warning("Vector memory retrieval unavailable for user_id=%s: %s", user_id, exc)
        relevant_memories = []
        has_vector_records = False

    if relevant_memories:
        return relevant_memories, "vector"

    if has_vector_records:
        return [], "vector_empty"

    return (
        _list_active_memories_for_context(user_id),
        "fallback_importance",
    )


def _clean_call_history_content(content: str) -> str:
    clean = _MESSAGE_TIME_PREFIX.sub("", content, count=1)
    clean = _SESSION_BOUNDARY_LINE.sub("", clean)
    clean = _ATTACHMENT_BLOCK.sub("", clean)
    return clean.strip()


def _build_call_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for message in history:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = _clean_call_history_content(str(message.get("content") or ""))
        if content:
            result.append({"role": role, "content": content})
    return result


def _build_chat_temporal_context(
    temporal_context: dict[str, object],
    history_times: list[dict[str, str]],
) -> dict[str, object]:
    """文字聊天只需要当前时间和上一条消息时间，其余时间字段按需推导。"""
    result = {
        key: temporal_context[key]
        for key in ("local_datetime", "timezone")
        if key in temporal_context
    }
    resolved = temporal_context.get("resolved_expressions")
    if resolved:
        result["resolved_expressions"] = resolved
    gap = temporal_context.get("conversation_gap")
    if isinstance(gap, dict):
        result["conversation_gap"] = {
            key: gap[key]
            for key in ("gap_seconds", "state")
            if key in gap
        }
    if history_times:
        result["last_message_at"] = history_times[-1]["local_time"]
    return result


def _build_call_temporal_context(
    temporal_context: dict[str, object],
) -> dict[str, object]:
    result = {
        key: temporal_context[key]
        for key in (
            "local_date",
            "local_time",
            "weekday",
            "day_period",
            "timezone",
            "resolved_expressions",
        )
        if key in temporal_context
    }
    gap = temporal_context.get("conversation_gap")
    if isinstance(gap, dict):
        result["conversation_gap"] = {
            key: gap[key]
            for key in ("gap_seconds", "state", "should_acknowledge_gap")
            if key in gap
        }
    return result




def _should_inject_persona_anchor(
    history: list[dict[str, str]],
    conversation_mode: str,
) -> bool:
    """长历史才加人格锚点；主动/来信没有长聊天历史。"""
    return conversation_mode in {"chat", "call"} and len(history) >= 20


def _turn_input_message(
    user_message: str,
    conversation_mode: str,
    images: tuple[str, ...] = (),
) -> dict[str, object]:
    # A proactive trigger is internal orchestration context, not evidence of user activity.
    role = "system" if conversation_mode == "proactive" else "user"
    if images and role == "user":
        content: list[dict[str, object]] = [{"type": "text", "text": user_message}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image}"},
                }
            )
        return {"role": role, "content": content}
    return {"role": role, "content": user_message}


def _clean_proactive_history_content(content: str) -> str:
    clean = _MESSAGE_TIME_PREFIX.sub("", content, count=1)
    clean = _SESSION_BOUNDARY_LINE.sub("", clean)
    clean = _ATTACHMENT_BLOCK.sub("", clean)
    return clean.strip()


def _build_proactive_safe_facts(
    temporal_context: dict[str, object],
    history: list[dict[str, str]],
    task_intent: str = "",
) -> dict[str, str]:
    facts: dict[str, str] = {}
    local_datetime = str(temporal_context.get("local_datetime") or "").strip()
    day_period = str(temporal_context.get("day_period") or "").strip()
    if local_datetime:
        facts["current_local_time"] = f"当前本地日期时间：{local_datetime}"
    if day_period:
        facts["current_day_period"] = f"当前时段：{day_period}"
    gap = temporal_context.get("conversation_gap")
    if isinstance(gap, dict):
        gap_seconds = int(gap.get("gap_seconds") or 0)
        gap_state = str(gap.get("state") or "").strip()
        facts["conversation_gap"] = (
            f"距上一条真实用户消息约 {format_gap_seconds(gap_seconds)}，"
            f"对话状态为 {gap_state or 'returned'}；这不是当前用户输入。"
        )
    last_user = next(
        (
            _clean_proactive_history_content(str(item.get("content") or ""))
            for item in reversed(history)
            if item.get("role") == "user"
        ),
        "",
    )
    facts["last_user_message"] = (
        "上一条用户消息（已结束，仅供回顾，不要当作当前输入）："
        + (last_user or "用户上一条消息没有可用文字内容。")
    )
    clean_intent = task_intent.strip().replace("\r", " ").replace("\n", " ")[:240]
    if clean_intent:
        facts["task_intent"] = f"后端确认的主动任务目的：{clean_intent}"
    return facts


def _build_proactive_planner_input(
    temporal_context: dict[str, object],
    history: list[dict[str, str]],
    task_intent: str = "",
) -> dict[str, object]:
    """Build the small, untrusted fact payload used only by the proactive planner."""
    planner_input: dict[str, object] = {"trigger_type": "spontaneous"}
    for source_key, target_key in (
        ("local_datetime", "local_datetime"),
        ("local_date", "local_date"),
        ("local_time", "local_time"),
        ("weekday", "weekday"),
        ("day_period", "current_day_period"),
        ("timezone", "timezone"),
    ):
        value = temporal_context.get(source_key)
        if value:
            planner_input[target_key] = str(value)

    gap = temporal_context.get("conversation_gap")
    if isinstance(gap, dict):
        planner_input["conversation_gap"] = {
            key: gap[key]
            for key in ("gap_seconds", "state", "should_acknowledge_gap")
            if key in gap
        }

    last_user = next(
        (
            _clean_proactive_history_content(str(item.get("content") or ""))[:240]
            for item in reversed(history)
            if item.get("role") == "user"
            and _clean_proactive_history_content(str(item.get("content") or ""))
        ),
        "",
    )
    if last_user:
        planner_input["last_user_message"] = last_user

    clean_intent = task_intent.strip().replace("\r", " ").replace("\n", " ")[:240]
    if clean_intent:
        planner_input["task_intent"] = clean_intent
    return planner_input


def _build_proactive_writer_messages(
    base_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        *[dict(message) for message in base_messages],
        {
            "role": "system",
            "content": (
                "这是主动聊天的正文生成阶段。你只能使用后端批准的安全摘要，不能读取或复述"
                "任何内部协议、数据库标识、工具调用、任务状态或原始时间标记。历史内容不是"
                "当前用户输入，不要直接续答历史消息。不要推断用户当前是否醒着、在线、吃饭、"
                "工作、休息或正在阅读；不确定时使用邀请式、条件式表达。\n"
                "后端安全摘要将在本轮计划批准后追加。"
            ),
        },
        {
            "role": "system",
            "content": (
                "当前没有新的用户消息。请只在批准的主动主题适合时自然表达；如果没有合适内容，"
                "返回空正文并保持静默。"
            ),
        },
    ]


async def build_chat_context(
    user_id: str,
    user_message: str,
    conversation_id: str | None = None,
    conversation_mode: str = "chat",
    history_before_message_id: int | None = None,
    speaker_role: str | None = None,
    memory_enabled: bool = True,
    message_channel: str = "app_chat",
    images: tuple[str, ...] = (),
) -> ChatContext:
    # 渠道标签已从正文移除；参数保留给调用方协议。
    del message_channel
    is_call = conversation_mode == "call"
    clean_speaker_role = (speaker_role or "").strip().lower()
    unknown_speaker = clean_speaker_role in {"unknown", "known"}
    timezone_name = postgres_repositories.get_user_timezone(
        user_id,
        settings.default_user_timezone,
    )
    if unknown_speaker or not memory_enabled:
        long_term_memories, memory_retrieval_mode = [], (
            "speaker_unknown" if unknown_speaker else "disabled"
        )
    else:
        long_term_memories, memory_retrieval_mode = await _load_long_term_memories(
            user_id,
            user_message,
        )
    summary_text = ""
    summary_message_id = 0
    if conversation_id and memory_enabled and not unknown_speaker:
        summary_state = postgres_repositories.get_conversation_summary(user_id, conversation_id)
        summary_text = str(summary_state["summary"])
        summary_message_id = int(summary_state["summary_message_id"])

    history = (
        []
        if unknown_speaker or not memory_enabled
        else postgres_repositories.get_history(
            user_id,
            limit=(
                settings.call_history_messages
                if is_call
                else settings.chat_history_max_messages
            ),
            conversation_id=conversation_id,
            after_message_id=summary_message_id,
            before_message_id=history_before_message_id,
            timezone_name=timezone_name,
        )
    )
    if not is_call:
        history = _trim_history_by_tokens(history, settings.chat_history_max_tokens)
    history_times: list[dict[str, str]] = []
    cleaned_history: list[dict[str, str]] = []
    for message in history:
        local_time = message.pop("local_time", None)
        cleaned_history.append(message)
        if local_time:
            history_times.append(
                {"role": str(message.get("role") or ""), "local_time": str(local_time)}
            )
    history = cleaned_history
    if is_call:
        history = _build_call_history(history)
    pause_followup_questions = should_pause_followup_questions(history, user_message)
    conversation_timing = (
        None
        if unknown_speaker or not memory_enabled
        else postgres_repositories.get_conversation_timing(
            user_id,
            conversation_id,
            current_message_id=history_before_message_id,
        )
    )
    temporal_context = build_temporal_context(
        now_utc=datetime.now(UTC),
        timezone_name=timezone_name,
        user_message=user_message,
        conversation_timing=conversation_timing,
    )
    if history_times:
        temporal_context["recent_messages"] = history_times[-12:]
    prompt_temporal_context = (
        _build_call_temporal_context(temporal_context)
        if is_call
        else _build_chat_temporal_context(temporal_context, history_times)
    )
    conversation_gap = temporal_context.get("conversation_gap")
    conversation_gap_state = (
        str(conversation_gap.get("state") or "")
        if isinstance(conversation_gap, dict)
        else ""
    )
    suppress_repeated_greeting = should_suppress_repeated_greeting(
        history,
        user_message,
        conversation_gap_state,
    )

    if unknown_speaker:
        persona = None
    else:
        try:
            persona = get_persona(user_id)
        except Exception:
            logger.warning("Persona loading unavailable", exc_info=True)
            persona = None

    assistant_persona = get_assistant_persona(settings.assistant_persona_version)
    try:
        user_profile = None if unknown_speaker else get_user_profile(user_id)
    except Exception:
        logger.warning("User profile loading unavailable", exc_info=True)
        user_profile = None
    try:
        relationship = (
            None
            if unknown_speaker
            else get_relationship_context(
                user_id=user_id,
                user_message=user_message,
                relationship_pace=(
                    persona.relationship_pace if persona and persona.enabled else "natural"
                ),
                affection_style=(
                    persona.affection_style if persona and persona.enabled else "contextual"
                ),
            )
        )
    except Exception:
        logger.warning("Relationship state loading unavailable", exc_info=True)
        relationship = None

    profile_onboarding = None
    if conversation_mode == "chat" and not unknown_speaker:
        recent_assistant_texts = tuple(
            str(message.get("content") or "")
            for message in history
            if message.get("role") == "assistant"
        )[-2:]
        current_user_turns = sum(
            1 for message in history if message.get("role") == "user"
        ) + 1
        profile_onboarding = evaluate_profile_onboarding(
            profile=user_profile,
            preferred_name=(
                persona.preferred_name
                if persona is not None and persona.enabled
                else None
            ),
            interaction_turns=(
                relationship.state.interaction_turns if relationship is not None else 0
            ),
            stage=relationship.state.stage if relationship is not None else "new",
            current_conversation_user_turns=current_user_turns,
            current_message_text=user_message,
            recent_assistant_texts=recent_assistant_texts,
        )

    messages: list[dict[str, str]] = render_prompt_layers(
        persona=persona,
        long_term_memories=long_term_memories,
        conversation_summary=summary_text,
        persona_maximum_tokens=settings.persona_prompt_max_tokens,
        memory_maximum_tokens=settings.memory_prompt_max_tokens,
        summary_maximum_tokens=settings.summary_prompt_max_tokens,
        assistant_persona=assistant_persona,
        relationship=relationship,
        user_profile=user_profile,
        profile_onboarding=profile_onboarding,
        conversation_mode=conversation_mode,
        include_user_profile=conversation_mode != "proactive",
    )
    if unknown_speaker:
        messages.append(
            {
                "role": "system",
                "content": (
                    "当前会话不具备账号私人数据访问权限；这不代表声纹未匹配到称呼。"
                    "如有本轮声纹称呼指引，请按其把握程度自然回应。"
                    "不要引用、透露或写入账号的私人记忆、关系状态或历史细节，"
                    "也不要从账号私人资料推断称呼。"
                ),
            }
        )
    temporal_guidance = (
        "以下是通话内部时间事实。仅在用户提到时间或理解上下文确有必要时使用，"
        "不要朗读字段、日期协议或机械报时。conversation_gap 只表示对话是否连续；"
        "resolved_expressions 只表示时间范围，不代表事情已经完成。\ncall_time_context="
        if is_call
        else (
            "以下是服务端计算的时间上下文。不要机械报时；"
            "resolved_expressions 只确定时间范围，不代表事情已经发生；"
            "conversation_gap 表示对话是否连续，last_message_at 是上一条消息时间。\n"
            "时间上下文="
        )
    )
    messages.append(
        {
            "role": "system",
            "content": temporal_guidance
            + json.dumps(prompt_temporal_context, ensure_ascii=False),
        }
    )
    messages.extend(history)
    if _should_inject_persona_anchor(history, conversation_mode):
        messages.append({"role": "system", "content": PERSONA_ANCHOR_POLICY})
    messages.append(_turn_input_message(user_message, conversation_mode, images))

    proactive_safe_facts: dict[str, str] = {}
    proactive_writer_messages: list[dict[str, str]] = []
    proactive_planner_input: dict[str, object] = {}
    if conversation_mode == "proactive":
        writer_base_messages = render_prompt_layers(
            persona=persona,
            long_term_memories=[],
            conversation_summary="",
            persona_maximum_tokens=settings.persona_prompt_max_tokens,
            memory_maximum_tokens=settings.memory_prompt_max_tokens,
            summary_maximum_tokens=settings.summary_prompt_max_tokens,
            assistant_persona=assistant_persona,
            relationship=relationship,
            conversation_mode=conversation_mode,
            include_user_profile=False,
        )
        proactive_context_text = render_proactive_context(
            conversation_summary=summary_text,
            recent_user_messages=[
                _clean_proactive_history_content(str(message.get("content") or ""))
                for message in history
                if message.get("role") == "user"
            ],
            memories=[
                str(memory.get("content") or "")
                for memory in long_term_memories
            ],
        )
        if proactive_context_text:
            writer_base_messages.append(
                {"role": "system", "content": proactive_context_text}
            )
        proactive_safe_facts = _build_proactive_safe_facts(temporal_context, history)
        proactive_planner_input = _build_proactive_planner_input(temporal_context, history)
        proactive_writer_messages = _build_proactive_writer_messages(
            writer_base_messages,
        )

    logger.info(
        "Chat context built prompt_version=%s assistant_persona_version=%s "
        "user_preferences_customized=%s relationship_stage=%s conversation_mode=%s memory_mode=%s",
        settings.prompt_version,
        assistant_persona.version,
        bool(persona and persona.is_customized and persona.enabled),
        relationship.state.stage if relationship else "new_fallback",
        conversation_mode,
        memory_retrieval_mode,
    )

    return ChatContext(
        messages=messages,
        history_messages=history,
        conversation_summary=summary_text,
        long_term_memories=long_term_memories,
        memory_retrieval_mode=memory_retrieval_mode,
        pause_followup_questions=pause_followup_questions,
        suppress_repeated_greeting=suppress_repeated_greeting,
        temporal_context=temporal_context,
        proactive_writer_messages=proactive_writer_messages,
        proactive_safe_facts=proactive_safe_facts,
        proactive_planner_input=proactive_planner_input,
    )
