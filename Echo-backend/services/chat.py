import logging
from dataclasses import dataclass
from typing import Optional

from llm_client import request_llm
from services.conversation_summary import maybe_update_conversation_summary
from services.context_builder import build_chat_context
from services.memory import add_message, ensure_conversation, get_or_create_active_conversation

logger = logging.getLogger(__name__)

class ChatValidationError(ValueError):
    """对话入参错误，例如缺少 user_id 或消息为空。"""

    pass


@dataclass
class ChatTurnResult:
    """一次完整对话轮次的结果，后续可扩展 token、记忆命中等调试信息。"""

    reply: str
    user_message: str
    user_message_id: int
    assistant_message_id: int
    conversation_id: str
    summary_updated: bool = False


async def generate_chat_reply(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
) -> ChatTurnResult:
    """统一处理文本/语音的核心对话流程。

    运行顺序：
    1. 校验并清洗用户输入。
    2. 加载短期历史并构建 messages。
    3. 调用大模型生成回复。
    4. 将用户消息和 assistant 回复写入同一套消息表。
    """
    clean_user_id = user_id.strip()
    clean_message = message.strip()

    if not clean_user_id:
        raise ChatValidationError("Missing user_id")
    if not clean_message:
        raise ChatValidationError("Empty message")

    # 没传 conversation_id 时，使用当前用户的 active 会话；传了则确保它存在。
    resolved_conversation_id = (
        ensure_conversation(clean_user_id, conversation_id)
        if conversation_id
        else get_or_create_active_conversation(clean_user_id)
    )

    # Context Builder 专门负责“给模型看什么”，Chat Service 只负责对话流程编排。
    context = build_chat_context(clean_user_id, clean_message, conversation_id=resolved_conversation_id)
    reply = await request_llm(context.messages)
    logger.info("LLM reply generated for user_id=%s", clean_user_id)

    user_message_id = add_message(
        clean_user_id,
        "user",
        clean_message,
        conversation_id=resolved_conversation_id,
        message_type=user_message_type,
    )
    assistant_message_id = add_message(
        clean_user_id,
        "assistant",
        reply,
        conversation_id=resolved_conversation_id,
        message_type=assistant_message_type,
    )

    summary_updated = False
    try:
        # 摘要是长对话优化能力，不应影响当前用户回复；失败只记录日志。
        summary_updated = await maybe_update_conversation_summary(clean_user_id, resolved_conversation_id)
    except Exception:
        logger.exception("Conversation summary update failed for conversation_id=%s", resolved_conversation_id)

    return ChatTurnResult(
        reply=reply,
        user_message=clean_message,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        conversation_id=resolved_conversation_id,
        summary_updated=summary_updated,
    )
