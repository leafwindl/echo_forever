import logging
from typing import Dict, List

from providers.llm_provider import get_llm_provider
from shared.config import settings

from features.chat.infrastructure import postgres_repositories

logger = logging.getLogger(__name__)


def _format_messages_for_summary(messages: List[Dict[str, object]]) -> str:
    lines = []
    for message in messages:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip()
        if content:
            message_id = int(message.get("id", 0))
            lines.append(f"message_id={message_id} role={role}: {content}")
    return "\n".join(lines)


def _build_summary_messages(
    existing_summary: str, messages_to_summarize: List[Dict[str, object]]
) -> list[dict]:
    conversation_text = _format_messages_for_summary(messages_to_summarize)
    prompt = (
        "你是 Echo 后端的会话摘要模块。请把下面的历史对话压缩为后续对话可用的中文摘要。\n"
        "要求：\n"
        "1. 只把 role=user 的原话归纳为用户事实、偏好、称呼、目标或边界；每条必须附 source_message_id。\n"
        "2. 保留必要的情绪脉络，但不要夸大或诊断。\n"
        "3. role=assistant 只用于理解指代，不得转写成用户事实；不要加入用户没有说过的信息。\n"
        "4. 如果已有旧摘要，请把新内容合并进去，输出一份更新后的完整摘要。\n"
        "5. 未完成话题放入 DORMANT_TOPICS，只表示历史状态，不能写成下一轮应主动追问的待办。\n"
        "6. 若旧摘要与带 message_id 的原话冲突，以原话为准并删除错误归属。\n"
        "7. 控制在 500 字以内，严格使用以下两个区块：\n"
        "[USER_FACTS]\n- source_message_id=<id> | <事实>\n[/USER_FACTS]\n"
        "[DORMANT_TOPICS]\n- source_message_id=<id> | <历史未完成话题>\n[/DORMANT_TOPICS]\n\n"
        f"已有摘要：\n{existing_summary or '无'}\n\n"
        f"需要合并的新对话：\n{conversation_text}"
    )
    return [
        {"role": "system", "content": "你负责为长期对话生成准确、克制、可用于上下文注入的摘要。"},
        {"role": "user", "content": prompt},
    ]


async def maybe_update_conversation_summary(user_id: str, conversation_id: str) -> bool:
    summary_state = postgres_repositories.get_conversation_summary(user_id, conversation_id)
    existing_summary = str(summary_state["summary"])
    summary_message_id = int(summary_state["summary_message_id"])

    unsummarized_messages = postgres_repositories.get_conversation_messages(
        user_id,
        conversation_id,
        after_message_id=summary_message_id,
    )

    trigger_messages = max(settings.conversation_summary_trigger_messages, 1)
    keep_recent_messages = max(settings.conversation_summary_keep_recent_messages, 0)

    if len(unsummarized_messages) <= trigger_messages:
        return False

    messages_to_summarize = (
        unsummarized_messages[:-keep_recent_messages]
        if keep_recent_messages
        else unsummarized_messages
    )
    if not messages_to_summarize:
        return False

    new_summary_boundary = int(messages_to_summarize[-1]["id"])
    messages = _build_summary_messages(existing_summary, messages_to_summarize)
    llm_provider = get_llm_provider()
    updated_summary = (
        await llm_provider.chat_completion(
            messages,
            temperature=settings.conversation_summary_temperature,
            max_tokens=settings.conversation_summary_max_tokens,
        )
    ).strip()

    if not updated_summary:
        logger.warning(
            "Conversation summary returned empty content for conversation_id=%s", conversation_id
        )
        return False

    postgres_repositories.update_conversation_summary(
        user_id=user_id,
        conversation_id=conversation_id,
        summary=updated_summary,
        summary_message_id=new_summary_boundary,
    )
    logger.info(
        "Conversation summary updated for user_id=%s conversation_id=%s boundary=%s",
        user_id,
        conversation_id,
        new_summary_boundary,
    )
    return True
