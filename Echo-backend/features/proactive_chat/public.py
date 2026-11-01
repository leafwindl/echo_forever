from __future__ import annotations

from features.proactive_chat.application.worker import ProcessProactiveChatJobs
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)

_worker: ProcessProactiveChatJobs | None = None


def get_proactive_repository() -> PostgresProactiveChatRepository:
    return PostgresProactiveChatRepository()


def get_proactive_worker() -> ProcessProactiveChatJobs:
    global _worker
    if _worker is None:
        from shared.config import settings

        from features.chat.infrastructure.adapters import InMemoryChatRequestGuard
        from features.chat.infrastructure.container import (
            get_delivery_timing_policy,
            get_generate_chat_reply_use_case,
        )
        from features.chat.infrastructure.events import get_chat_event_broker

        _worker = ProcessProactiveChatJobs(
            repository=get_proactive_repository(),
            reply_generator=get_generate_chat_reply_use_case(),
            request_guard=InMemoryChatRequestGuard(),
            event_broker=get_chat_event_broker(),
            timing_policy=get_delivery_timing_policy(),
            lease_seconds=settings.proactive_chat_job_lease_seconds,
        )
    return _worker


async def process_proactive_chat_once() -> bool:
    return await get_proactive_worker().run_once()


def reset_user_proactive_state(user_id: str) -> None:
    """Reset preferences, reminders and queued jobs for a new companionship cycle."""
    get_proactive_repository().reset_user_state(user_id)


__all__ = [
    "get_proactive_repository",
    "process_proactive_chat_once",
    "reset_user_proactive_state",
]
