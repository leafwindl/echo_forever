from typing import Optional

from features.chat.domain.entities import (
    ChatContextClearResult,
    ChatReplyDeliveryResult,
    ChatRequestInProgressError,
    ChatTurnResult,
    ChatValidationError,
)
from features.chat.infrastructure.container import (
    get_clear_chat_context_use_case,
    get_generate_chat_reply_use_case,
    get_send_chat_message_use_case,
)


def clear_chat_context(user_id: str) -> ChatContextClearResult:
    return get_clear_chat_context_use_case().execute(user_id)


async def generate_chat_reply(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
    conversation_mode: str = "chat",
) -> ChatTurnResult:
    use_case = get_generate_chat_reply_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        conversation_id=conversation_id,
        user_message_type=user_message_type,
        assistant_message_type=assistant_message_type,
        conversation_mode=conversation_mode,
    )


async def send_chat_message(
    user_id: str,
    message: str,
    conversation_mode: str = "chat",
) -> ChatReplyDeliveryResult:
    use_case = get_send_chat_message_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        conversation_mode=conversation_mode,
    )


__all__ = [
    "ChatContextClearResult",
    "ChatReplyDeliveryResult",
    "ChatRequestInProgressError",
    "ChatTurnResult",
    "ChatValidationError",
    "clear_chat_context",
    "generate_chat_reply",
    "send_chat_message",
]
