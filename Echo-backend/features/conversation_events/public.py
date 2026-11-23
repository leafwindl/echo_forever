from __future__ import annotations

from datetime import datetime
from typing import Any

from features.conversation_events.application.record_event import RecordConversationEvent
from features.conversation_events.domain.entities import (
    ACTOR_ECHO,
    ACTOR_SYSTEM,
    ACTOR_USER,
    EVENT_MESSAGE,
    EVENT_SEND,
    EVENT_SHARE,
    EVENT_TOOL_CALL,
    ConversationEvent,
)
from features.conversation_events.infrastructure.postgres_repository import (
    PostgresConversationEventRepository,
)


def _repository() -> PostgresConversationEventRepository:
    return PostgresConversationEventRepository()


def record_conversation_event(
    *,
    event_type: str,
    source: str,
    actor: str,
    user_id: str,
    conversation_id: str | None = None,
    turn_id: str = "",
    content: str = "",
    payload: dict[str, Any] | None = None,
    source_created_at: datetime | None = None,
) -> int:
    """记录一条会话事件；失败由调用方决定是否吞掉。"""
    return RecordConversationEvent(_repository()).execute(
        ConversationEvent(
            event_type=event_type,
            source=source,
            actor=actor,
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            content=content,
            payload=payload or {},
            source_created_at=source_created_at,
        )
    )


def list_conversation_events(
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 50,
) -> list[ConversationEvent]:
    """按时间顺序读回一段会话的事件流。"""
    return _repository().list_for_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
    )


__all__ = [
    "ACTOR_ECHO",
    "ACTOR_SYSTEM",
    "ACTOR_USER",
    "EVENT_MESSAGE",
    "EVENT_SEND",
    "EVENT_SHARE",
    "EVENT_TOOL_CALL",
    "ConversationEvent",
    "list_conversation_events",
    "record_conversation_event",
]
