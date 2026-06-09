from typing import Optional

from features.chat.domain.entities import ChatTurnResult, ChatValidationError
from features.chat.infrastructure.container import get_generate_chat_reply_use_case


async def generate_chat_reply(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
) -> ChatTurnResult:
    use_case = get_generate_chat_reply_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        conversation_id=conversation_id,
        user_message_type=user_message_type,
        assistant_message_type=assistant_message_type,
    )


__all__ = [
    "ChatTurnResult",
    "ChatValidationError",
    "generate_chat_reply",
]
