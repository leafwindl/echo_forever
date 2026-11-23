from __future__ import annotations

from datetime import datetime
from typing import Protocol

from features.presence.domain.entities import (
    PresenceContext,
    PresenceMemory,
    PresenceState,
    PresenceThought,
    ThoughtDraft,
)


class PresenceRepository(Protocol):
    def get_or_create_state(self, user_id: str) -> PresenceState: ...

    def save_state(self, state: PresenceState) -> None: ...

    def recent_thoughts(self, user_id: str, limit: int) -> list[PresenceThought]: ...

    def add_thought(self, thought: PresenceThought) -> None: ...

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        detail: dict,
        now: datetime,
    ) -> None: ...


class PresenceContextSource(Protocol):
    async def load(self, user_id: str, limit: int) -> PresenceContext: ...

    def recent_user_ids(self, limit: int) -> tuple[str, ...]: ...


class PresenceMemorySource(Protocol):
    async def recall(self, user_id: str, query: str) -> PresenceMemory | None: ...


class PresenceThoughtGenerator(Protocol):
    async def generate(
        self,
        *,
        state: PresenceState,
        context: PresenceContext,
        memory: PresenceMemory | None,
        recent_thoughts: tuple[PresenceThought, ...],
        now: datetime,
    ) -> ThoughtDraft: ...


class PresenceQuietHours(Protocol):
    def is_quiet(self, user_id: str, now: datetime) -> bool: ...

    def can_send_spontaneous(self, user_id: str, now: datetime) -> bool: ...


class PresenceMemoryWriter(Protocol):
    async def remember(self, *, user_id: str, text: str, salience: float) -> str | None: ...


class PresenceGoalCreator(Protocol):
    """把一次主动意图交给统一投递通道，返回目标 id。

    presence 不再直接写聊天消息：投递（推送、重试、并发保护）由 proactive job
    通道统一负责。
    """

    def create_goal(
        self,
        *,
        user_id: str,
        intent: str,
        draft_text: str,
        trigger_type: str = "presence",
        trigger_ref: str = "",
        action_intent: str = "",
        plan: str = "",
    ) -> str: ...
