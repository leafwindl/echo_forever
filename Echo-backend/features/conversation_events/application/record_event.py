from __future__ import annotations

from features.conversation_events.domain.entities import ConversationEvent
from features.conversation_events.domain.repositories import ConversationEventRepository


class RecordConversationEvent:
    """把一条事件追加进统一时间线。"""

    def __init__(self, repository: ConversationEventRepository):
        self.repository = repository

    def execute(self, event: ConversationEvent) -> int:
        return self.repository.append(event)
