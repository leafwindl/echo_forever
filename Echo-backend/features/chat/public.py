from collections.abc import Awaitable, Callable

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    ChatContextClearResult,
    ChatHistoryPage,
    ChatMessageAcceptance,
    ChatReplyDeliveryResult,
    ChatRequestInProgressError,
    ChatTurnResult,
    ChatValidationError,
    ExternalAssistantDelivery,
)
from features.chat.infrastructure.container import (
    get_accept_chat_message_use_case,
    get_clear_chat_context_use_case,
    get_generate_chat_reply_use_case,
    get_list_chat_messages_use_case,
    get_process_pending_chat_turns_use_case,
    get_send_chat_message_use_case,
)
from features.chat.infrastructure.events import ChatEvent, get_chat_event_broker
from features.chat.infrastructure.postgres_repositories import add_external_assistant_message


def clear_chat_context(user_id: str) -> ChatContextClearResult:
    return get_clear_chat_context_use_case().execute(user_id)


def accept_chat_message(
    *,
    user_id: str,
    client_message_id: str,
    message_type: str,
    text: str = "",
    content_parts: tuple[ContentPart, ...] = (),
) -> ChatMessageAcceptance:
    return get_accept_chat_message_use_case().execute(
        user_id=user_id,
        client_message_id=client_message_id,
        message_type=message_type,
        text=text,
        content_parts=content_parts,
    )


async def process_pending_chat_turn_once() -> bool:
    return await get_process_pending_chat_turns_use_case().run_once()


def list_chat_messages(
    user_id: str,
    before_id: int | None = None,
    after_id: int | None = None,
    limit: int = 10,
) -> ChatHistoryPage:
    return get_list_chat_messages_use_case().execute(
        user_id,
        before_id=before_id,
        after_id=after_id,
        limit=limit,
    )


async def generate_chat_reply(
    user_id: str,
    message: str,
    conversation_id: str | None = None,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
    conversation_mode: str = "chat",
    sticker_intent: str = "",
    user_content_parts: tuple[ContentPart, ...] = (),
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
) -> ChatTurnResult:
    use_case = get_generate_chat_reply_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        conversation_id=conversation_id,
        user_message_type=user_message_type,
        assistant_message_type=assistant_message_type,
        conversation_mode=conversation_mode,
        sticker_intent=sticker_intent,
        user_content_parts=user_content_parts,
        on_text_delta=on_text_delta,
    )


async def send_chat_message(
    user_id: str,
    message: str,
    conversation_mode: str = "chat",
    user_message_type: str = "text",
    sticker_intent: str = "",
    user_content_parts: tuple[ContentPart, ...] = (),
    request_id: str = "",
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    synthesize_voice: bool = True,
) -> ChatReplyDeliveryResult:
    use_case = get_send_chat_message_use_case()
    return await use_case.execute(
        user_id=user_id,
        message=message,
        conversation_mode=conversation_mode,
        user_message_type=user_message_type,
        sticker_intent=sticker_intent,
        user_content_parts=user_content_parts,
        request_id=request_id,
        on_text_delta=on_text_delta,
        synthesize_voice=synthesize_voice,
    )


async def deliver_external_assistant_message(
    *,
    user_id: str,
    content: str,
    idempotency_key: str,
    source: str,
) -> ExternalAssistantDelivery:
    delivery = add_external_assistant_message(
        user_id=user_id,
        content=content,
        idempotency_key=idempotency_key,
        source=source,
    )
    if delivery.replayed:
        return delivery
    message = delivery.message
    await get_chat_event_broker().publish(
        user_id,
        ChatEvent(
            event="chat.delivery.created",
            data={
                "turn_id": "",
                "reply_group_id": message.reply_group_id,
                "conversation_id": delivery.conversation_id,
                "origin": source,
                "presentation": {
                    "agent_elapsed_ms": 0,
                    "initial_delay_ms": 0,
                    "message_delays_ms": [0],
                },
                "messages": [
                    {
                        "message_id": message.message_id,
                        "stable_message_id": message.stable_message_id,
                        "client_message_id": message.client_message_id,
                        "role": message.role,
                        "message_type": message.message_type,
                        "content": message.content,
                        "content_parts": [],
                        "sources": [],
                        "agent_turn_id": message.agent_turn_id,
                        "reply_group_id": message.reply_group_id,
                        "sequence_in_group": message.sequence_in_group,
                        "in_reply_to_message_id": message.in_reply_to_message_id,
                        "created_at": message.created_at.isoformat(),
                    }
                ],
            },
        ),
    )
    return delivery


__all__ = [
    "ChatContextClearResult",
    "ChatHistoryPage",
    "ChatMessageAcceptance",
    "ChatReplyDeliveryResult",
    "ChatRequestInProgressError",
    "ChatTurnResult",
    "ChatValidationError",
    "ExternalAssistantDelivery",
    "clear_chat_context",
    "deliver_external_assistant_message",
    "accept_chat_message",
    "generate_chat_reply",
    "list_chat_messages",
    "process_pending_chat_turn_once",
    "send_chat_message",
]
