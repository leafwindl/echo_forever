import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from llm_client import request_llm
from services.memory import add_message, get_history

logger = logging.getLogger(__name__)

# 统一控制短期上下文窗口：1 轮 = user 1 条 + assistant 1 条。
MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2


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


def build_basic_messages(user_id: str, user_message: str, conversation_id: Optional[str] = None) -> list[dict]:
    """构建当前 v0.2 第二阶段的基础上下文。

    这一层先保持 v0.1 的行为：系统 Prompt + 最近 N 条历史 + 当前用户消息。
    第三阶段的 Context Builder 会从这里接入会话摘要和长期记忆。
    """
    history = get_history(user_id, limit=MAX_HISTORY_MESSAGES, conversation_id=conversation_id)

    messages = [{"role": "system", "content": settings.system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


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

    messages = build_basic_messages(clean_user_id, clean_message, conversation_id=conversation_id)
    reply = await request_llm(messages)
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
