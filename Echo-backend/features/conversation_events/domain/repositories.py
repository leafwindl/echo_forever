from __future__ import annotations

from typing import Protocol

from features.conversation_events.domain.entities import ConversationEvent


class ConversationEventRepository(Protocol):
    def append(self, event: ConversationEvent) -> int: ...

    def list_for_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int = 50,
    ) -> list[ConversationEvent]: ...
