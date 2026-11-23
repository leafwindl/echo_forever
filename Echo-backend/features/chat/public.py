import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    CHAT_CHANNEL_APP,
    CHAT_CHANNEL_WECHAT,
    CHAT_VISIBILITY_MAIN,
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
from features.chat.infrastructure.postgres_repositories import (
    add_external_assistant_message,
    list_recent_assistant_contents,
)
from features.chat.infrastructure.postgres_repositories import (
    list_recent_chat_user_ids as _list_recent_chat_user_ids,
)
from features.conversation_events.public import (
    ACTOR_ECHO,
    EVENT_MESSAGE,
    record_conversation_event,
)

logger = logging.getLogger(__name__)


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


def list_recent_assistant_contents_for_guard(
    user_id: str,
    limit: int = 12,
) -> tuple[str, ...]:
    return list_recent_assistant_contents(user_id, limit)


def list_recent_chat_user_ids(limit: int = 100) -> tuple[str, ...]:
    """Stable read entry for the presence heartbeat's candidate users."""
    return _list_recent_chat_user_ids(limit)


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
    user_images: tuple[str, ...] = (),
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    on_progress_text: Callable[[str], Awaitable[None]] | None = None,
    tools_enabled: bool | None = None,
    message_channel: str = CHAT_CHANNEL_APP,
    message_visibility: str = CHAT_VISIBILITY_MAIN,
    speaker_role: str | None = None,
    speaker_confidence: float = 0.0,
    speaker_name: str | None = None,
    memory_enabled: bool = True,
    source_created_at: datetime | None = None,
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
        user_images=user_images,
        on_text_delta=on_text_delta,
        on_progress_text=on_progress_text,
        tools_enabled=tools_enabled,
        message_channel=message_channel,
        message_visibility=message_visibility,
        speaker_role=speaker_role,
        speaker_confidence=speaker_confidence,
        speaker_name=speaker_name,
        memory_enabled=memory_enabled,
        source_created_at=source_created_at,
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
    on_progress_text: Callable[[str], Awaitable[None]] | None = None,
    synthesize_voice: bool = True,
    tools_enabled: bool | None = None,
    message_channel: str = CHAT_CHANNEL_APP,
    message_visibility: str = CHAT_VISIBILITY_MAIN,
    speaker_role: str | None = None,
    speaker_confidence: float = 0.0,
    speaker_name: str | None = None,
    memory_enabled: bool = True,
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
        on_progress_text=on_progress_text,
        synthesize_voice=synthesize_voice,
        tools_enabled=tools_enabled,
        message_channel=message_channel,
        message_visibility=message_visibility,
        speaker_role=speaker_role,
        speaker_confidence=speaker_confidence,
        speaker_name=speaker_name,
        memory_enabled=memory_enabled,
    )


def record_internal_assistant_note(
    *,
    user_id: str,
    conversation_id: str,
    content: str,
    source: str = "agent_action",
) -> int:
    """记录一次纯动作的结果：不进客户端展示，但会进聊天上下文。"""
    from features.chat.infrastructure.postgres_repositories import (
        add_internal_assistant_note,
    )

    message_id = add_internal_assistant_note(
        user_id=user_id,
        conversation_id=conversation_id,
        content=content,
        source=source,
    )
    try:
        record_conversation_event(
            event_type=EVENT_MESSAGE,
            source=source,
            actor=ACTOR_ECHO,
            user_id=user_id,
            conversation_id=conversation_id,
            content=content,
            payload={
                "message_id": message_id,
                "message_type": "text",
                "visibility": "internal",
            },
        )
    except Exception:
        logger.warning("record internal assistant event failed", exc_info=True)
    return message_id


async def deliver_external_assistant_message(
    *,
    user_id: str,
    content: str,
    idempotency_key: str,
    source: str,
    content_parts: tuple[ContentPart, ...] = (),
) -> ExternalAssistantDelivery:
    delivery = add_external_assistant_message(
        user_id=user_id,
        content=content,
        idempotency_key=idempotency_key,
        source=source,
        content_parts=content_parts,
    )
    if delivery.replayed:
        return delivery
    message = delivery.message
    try:
        record_conversation_event(
            event_type=EVENT_MESSAGE,
            source=source,
            actor=ACTOR_ECHO,
            user_id=user_id,
            conversation_id=delivery.conversation_id,
            content=message.content,
            payload={
                "message_id": message.message_id,
                "message_type": message.message_type,
            },
            source_created_at=message.created_at,
        )
    except Exception:
        logger.warning("record external assistant event failed", exc_info=True)
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
    "CHAT_CHANNEL_WECHAT",
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
    "list_recent_chat_user_ids",
    "process_pending_chat_turn_once",
    "record_internal_assistant_note",
    "send_chat_message",
]
