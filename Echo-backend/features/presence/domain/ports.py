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


class PresenceMessageComposer(Protocol):
    async def compose(
        self,
        *,
        thought: PresenceThought,
        context: PresenceContext,
        now: datetime,
    ) -> str: ...


class PresenceActionExecutor(Protocol):
    async def execute(
        self,
        *,
        user_id: str,
        action_intent: str,
        thought_id: str,
    ) -> str: ...


class PresenceMemoryWriter(Protocol):
    async def remember(self, *, user_id: str, text: str, salience: float) -> str | None: ...


class PresenceMessageDelivery(Protocol):
    async def deliver(
        self,
        *,
        user_id: str,
        thought_id: str,
        text: str,
    ) -> bool: ...
