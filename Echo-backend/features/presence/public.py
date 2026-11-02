from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def build_presence_cue(user_id: str, *, now: datetime | None = None) -> str:
    """Small continuity cue for chat generation; facts only, not instructions."""
    current = now or datetime.now(UTC)
    state = get_presence_state(user_id)
    thoughts = list_presence_thoughts(user_id, 1)
    if not thoughts:
        return ""
    latest = thoughts[0]
    if latest.created_at is not None and current - latest.created_at > timedelta(hours=8):
        return ""
    return (
        "[Echo 的内部状态，只用于保持连续感，不是用户消息，也不要直接复述]\n"
        f"当前状态：{state.status}。\n"
        f"最近一次独处念头：{latest.text}\n"
        "如果它和当前话题无关，就忽略它；不要假装自己刚刚一直在等用户。"
    )


async def process_presence_once() -> int:
    return await get_presence_service().run_once()


__all__ = [
    "PresenceState",
    "PresenceThought",
    "PresenceTickResult",
    "build_presence_cue",
    "get_presence_state",
    "list_presence_thoughts",
    "process_presence_once",
    "run_presence_tick",
]
