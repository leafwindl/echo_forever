import logging
from typing import Dict, List

from llm_client import request_llm
from services.memory import (
    get_conversation_messages,
    get_conversation_summary,
    update_conversation_summary,
)

logger = logging.getLogger(__name__)

# 触发阈值：未被摘要覆盖的消息超过这个数量时，才调用 LLM 做压缩。
SUMMARY_TRIGGER_MESSAGES = 24

# 保留最近消息原文，不写进摘要，保证模型仍能看到最新语气和细节。
SUMMARY_KEEP_RECENT_MESSAGES = 12


def _format_messages_for_summary(messages: List[Dict[str, object]]) -> str:
    lines = []
    for message in messages:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_summary_messages(existing_summary: str, messages_to_summarize: List[Dict[str, object]]) -> list[dict]:
    """构建摘要请求。

    摘要本身不是直接给用户看的，而是给后续对话作为压缩上下文使用；
    因此要求它保留事实、偏好、未完成话题和情绪脉络，避免文学化扩写。
    """
    conversation_text = _format_messages_for_summary(messages_to_summarize)
    prompt = (
        "你是 Echo 后端的会话摘要模块。请把下面的历史对话压缩为后续对话可用的中文摘要。\n"
        "要求：\n"
        "1. 保留用户明确说过的重要事实、偏好、称呼、目标、困扰和未完成话题。\n"
        "2. 保留必要的情绪脉络，但不要夸大或诊断。\n"
        "3. 不要加入用户没有说过的信息。\n"
        "4. 如果已有旧摘要，请把新内容合并进去，输出一份更新后的完整摘要。\n"
        "5. 控制在 500 字以内，使用短段落或项目符号。\n\n"
        f"已有摘要：\n{existing_summary or '无'}\n\n"
        f"需要合并的新对话：\n{conversation_text}"
    )
    return [
        {"role": "system", "content": "你负责为长期对话生成准确、克制、可用于上下文注入的摘要。"},
        {"role": "user", "content": prompt},
    ]


async def maybe_update_conversation_summary(user_id: str, conversation_id: str) -> bool:
    """必要时更新会话滚动摘要。

    返回 True 表示本轮确实更新了摘要；False 表示消息还不够多或没有可摘要内容。
    调用方通常不应让摘要失败影响用户当前回复，所以 Chat Service 会捕获异常。
    """
    summary_state = get_conversation_summary(user_id, conversation_id)
    existing_summary = str(summary_state["summary"])
    summary_message_id = int(summary_state["summary_message_id"])

    unsummarized_messages = get_conversation_messages(
        user_id,
        conversation_id,
        after_message_id=summary_message_id,
    )

    if len(unsummarized_messages) <= SUMMARY_TRIGGER_MESSAGES:
        return False

    messages_to_summarize = unsummarized_messages[:-SUMMARY_KEEP_RECENT_MESSAGES]
    if not messages_to_summarize:
        return False

    new_summary_boundary = int(messages_to_summarize[-1]["id"])
    messages = _build_summary_messages(existing_summary, messages_to_summarize)
    updated_summary = (await request_llm(messages)).strip()

    if not updated_summary:
        logger.warning("Conversation summary returned empty content for conversation_id=%s", conversation_id)
        return False

    update_conversation_summary(
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
