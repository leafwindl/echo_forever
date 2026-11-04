import json
import logging
import re
from datetime import UTC, datetime

from shared.config import settings
from shared.prompting.renderer import (
    render_prompt_layers,
    render_turn_focus_guidance,
)

from features.assistant_persona.public import get_assistant_persona
from features.chat.domain.dialogue_style import (
    should_pause_followup_questions,
    should_suppress_repeated_greeting,
)
from features.chat.domain.entities import CHANNEL_LABELS, ChatContext
from features.chat.domain.temporal_context import build_temporal_context, format_gap_seconds
from features.chat.infrastructure import postgres_repositories
from features.memory.public import (
    list_memories,
    list_memory_embedding_records,
    retrieve_relevant_memories,
)
from features.persona.public import get_persona
from features.relationship.public import get_relationship_context

logger = logging.getLogger(__name__)

MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2
MAX_LONG_TERM_MEMORIES = 8




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
_CALL_EXTENDED_CONTEXT_PATTERN = re.compile(
    r"(?:还记得|记得吗|记不记得|我说过|我们聊过|你知道我|"
    r"(?:之前|以前|上次).{0,8}(?:我|我们|说|聊|提|事情|话题)|"
    r"继续.{0,8}(?:之前|上次|话题))"
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


def _call_requires_extended_context(user_message: str) -> bool:
    return bool(_CALL_EXTENDED_CONTEXT_PATTERN.search(user_message.strip()))


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




def _turn_input_message(
    user_message: str,
    conversation_mode: str,
    message_channel: str = "app_chat",
) -> dict[str, str]:
    # A proactive trigger is internal orchestration context, not evidence of user activity.
    role = "system" if conversation_mode == "proactive" else "user"
    channel_label = CHANNEL_LABELS.get(message_channel)
    content = (
        f"[{channel_label}] {user_message}"
        if role == "user" and channel_label
        else user_message
    )
    return {"role": role, "content": content}


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
) -> ChatContext:
    is_call = conversation_mode == "call"
    use_extended_call_context = is_call and _call_requires_extended_context(user_message)
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
    elif is_call and not use_extended_call_context:
        long_term_memories, memory_retrieval_mode = [], "call_skipped"
    else:
        long_term_memories, memory_retrieval_mode = await _load_long_term_memories(
            user_id,
            user_message,
        )
    summary_text = ""
    summary_message_id = 0
    if (
        conversation_id
        and (not is_call or use_extended_call_context)
        and memory_enabled
        and not unknown_speaker
    ):
        summary_state = postgres_repositories.get_conversation_summary(user_id, conversation_id)
        summary_text = str(summary_state["summary"])
        summary_message_id = int(summary_state["summary_message_id"])

    history = (
        []
        if unknown_speaker or not memory_enabled
        else postgres_repositories.get_history(
            user_id,
            limit=settings.call_history_messages if is_call else MAX_HISTORY_MESSAGES,
            conversation_id=conversation_id,
            after_message_id=summary_message_id,
            before_message_id=history_before_message_id,
            timezone_name=timezone_name,
        )
    )
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
    prompt_temporal_context = (
        _build_call_temporal_context(temporal_context) if is_call else temporal_context
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

    messages: list[dict[str, str]] = render_prompt_layers(
        product_identity=settings.system_prompt,
        persona=persona,
        long_term_memories=long_term_memories,
        conversation_summary=summary_text,
        prompt_version=settings.prompt_version,
        persona_maximum_tokens=settings.persona_prompt_max_tokens,
        memory_maximum_tokens=settings.memory_prompt_max_tokens,
        summary_maximum_tokens=settings.summary_prompt_max_tokens,
        assistant_persona=assistant_persona,
        relationship=relationship,
        conversation_mode=conversation_mode,
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
    messages.append(
        {
            "role": "system",
            "content": render_turn_focus_guidance(
                pause_followup_questions,
                suppress_repeated_greeting,
            ),
        }
    )
    messages.append(
        {
            "role": "system",
            "content": (
                "历史消息可能带有 [主客户端] 或 [微信端] 渠道标签，表示用户当时从哪个入口说话。"
                "标签只是内部上下文，不要朗读、不要暴露，也不要在回复里说“主客户端/微信端”。"
                "回应只发给触发本轮的用户入口，不要假设会自动同步到另一个入口。"
            ),
        }
    )
    temporal_guidance = (
        "以下是通话内部时间事实。仅在用户提到时间或理解上下文确有必要时使用，"
        "不要朗读字段、日期协议或机械报时。conversation_gap 只表示对话是否连续；"
        "resolved_expressions 只表示时间范围，不代表事情已经完成。\ncall_time_context="
        if is_call
        else (
            "以下是服务端计算的时间上下文，优先于模型自行猜测。不要机械报时，也不要每次都提时间。"
            "resolved_expressions 只确定时间范围，不代表对应事情已经发生或完成；"
            "relation_to_now=current/future 时尤其不能用已经完成的口吻追问结果。"
            "conversation_gap 的 active/recent 表示持续对话，不提离开；"
            "returned/long_absence 只在轻松闲聊、问候或分享近况时允许自然问候一次，"
            "事实问题、任务指令、报错和严肃话题不要插入。\ntemporal_context="
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
    messages.append(_turn_input_message(user_message, conversation_mode, message_channel))

    proactive_safe_facts: dict[str, str] = {}
    proactive_writer_messages: list[dict[str, str]] = []
    proactive_planner_input: dict[str, object] = {}
    if conversation_mode == "proactive":
        writer_base_messages = render_prompt_layers(
            product_identity=settings.system_prompt,
            persona=persona,
            long_term_memories=[],
            conversation_summary="",
            prompt_version=settings.prompt_version,
            persona_maximum_tokens=settings.persona_prompt_max_tokens,
            memory_maximum_tokens=settings.memory_prompt_max_tokens,
            summary_maximum_tokens=settings.summary_prompt_max_tokens,
            assistant_persona=assistant_persona,
            relationship=relationship,
            conversation_mode=conversation_mode,
        )
        writer_base_messages.append(
            {
                "role": "system",
                "content": render_turn_focus_guidance(
                    pause_followup_questions,
                    suppress_repeated_greeting,
                ),
            }
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
