import logging
from dataclasses import dataclass
from typing import Optional

from llm_client import request_llm
from services.context_builder import build_chat_context
from services.memory import add_message

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

    # Context Builder 专门负责“给模型看什么”，Chat Service 只负责对话流程编排。
    context = build_chat_context(clean_user_id, clean_message, conversation_id=conversation_id)
    reply = await request_llm(context.messages)
    logger.info("LLM reply generated for user_id=%s", clean_user_id)

    user_message_id = add_message(
        clean_user_id,
        "user",
        clean_message,
        conversation_id=conversation_id,
        message_type=user_message_type,
    )
    assistant_message_id = add_message(
        clean_user_id,
        "assistant",
        reply,
        conversation_id=conversation_id,
        message_type=assistant_message_type,
    )

    return ChatTurnResult(
        reply=reply,
        user_message=clean_message,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
    )
