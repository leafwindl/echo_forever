from __future__ import annotations

from datetime import datetime

from features.presence.domain.entities import (
    PresenceState,
    PresenceThought,
    PresenceTickResult,
)
from features.presence.infrastructure.container import get_presence_service


def get_presence_state(user_id: str) -> PresenceState:
    return get_presence_service().state(user_id)


def list_presence_thoughts(user_id: str, limit: int = 20) -> list[PresenceThought]:
    return get_presence_service().thoughts(user_id, limit)


async def run_presence_tick(user_id: str, *, now: datetime | None = None) -> PresenceTickResult:
    return await get_presence_service().tick(user_id, now=now)


async def process_presence_once() -> int:
    return await get_presence_service().run_once()


__all__ = [
    "PresenceState",
    "PresenceThought",
    "PresenceTickResult",
    "get_presence_state",
    "list_presence_thoughts",
    "process_presence_once",
    "run_presence_tick",
]
