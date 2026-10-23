from typing import Protocol

from features.relationship.domain.entities import RelationshipSignal, RelationshipState


class RelationshipRepository(Protocol):
    def get_or_create(self, user_id: str) -> RelationshipState: ...

    def count_active_memories(self, user_id: str) -> int: ...

    def save_progress(
        self,
        state: RelationshipState,
        signals: tuple[RelationshipSignal, ...],
        source_message_id: int | None,
    ) -> RelationshipState: ...

    def reset(self, user_id: str) -> RelationshipState: ...

    def update_mode(self, user_id: str, relationship_mode: str) -> RelationshipState: ...

