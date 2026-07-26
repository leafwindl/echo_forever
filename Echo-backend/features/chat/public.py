from collections.abc import Awaitable, Callable
from typing import Optional

from features.chat.domain.entities import (
    ChatReplyDeliveryResult,
    ChatRequestInProgressError,
    ChatTurnResult,
    ChatValidationError,
)
from features.chat.infrastructure.container import (
    get_generate_chat_reply_use_case,
    get_send_chat_message_use_case,
)


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


async def send_chat_message(
    user_id: str,
    message: str,
    input_type: str = "text",
    voice_reply_enabled: bool = False,
) -> ChatReplyDeliveryResult:
    use_case = get_send_chat_message_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        input_type=input_type,
        voice_reply_enabled=voice_reply_enabled,
    )


async def stream_chat_message(
    user_id: str,
    message: str,
    on_text_delta: Callable[[str], Awaitable[None]],
    on_audio_ready: Callable[[str], Awaitable[None]],
    input_type: str = "text",
    voice_reply_enabled: bool = False,
) -> ChatReplyDeliveryResult:
    use_case = get_send_chat_message_use_case()
    return await use_case.execute_stream(
        user_id=user_id,
        message=message,
        on_text_delta=on_text_delta,
        on_audio_ready=on_audio_ready,
        input_type=input_type,
        voice_reply_enabled=voice_reply_enabled,
    )


__all__ = [
    "ChatReplyDeliveryResult",
    "ChatRequestInProgressError",
    "ChatTurnResult",
    "ChatValidationError",
    "generate_chat_reply",
    "send_chat_message",
    "stream_chat_message",
]
