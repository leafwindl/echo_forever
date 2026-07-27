from datetime import datetime, timezone

from features.relationship.domain.entities import RelationshipContext, RelationshipState
from features.relationship.domain.repositories import RelationshipRepository
from features.relationship.domain.rules import (
    advance_relationship_state,
    build_relationship_context,
)


class RelationshipManagementService:
    def __init__(self, repository: RelationshipRepository):
        self.repository = repository

    def get_context(
        self,
        user_id: str,
        user_message: str,
        relationship_pace: str,
        affection_style: str,
    ) -> RelationshipContext:
        state = self.repository.get_or_create(user_id.strip())
        return build_relationship_context(
            state,
            user_message,
            relationship_pace,
            affection_style,
        )

    def record_turn(
        self,
        user_id: str,
        user_message: str,
        source_message_id: int | None,
        relationship_pace: str,
    ) -> RelationshipState:
        clean_user_id = user_id.strip()
        state = self.repository.get_or_create(clean_user_id)
        now = datetime.now(timezone.utc)
        progress = advance_relationship_state(
            state,
            observed_date=now.date().isoformat(),
            observed_at=now.isoformat(),
            shared_memory_count=self.repository.count_active_memories(clean_user_id),
            user_message=user_message,
            relationship_pace=relationship_pace,
        )
        return self.repository.save_progress(
            progress.state,
            progress.signals,
            source_message_id,
        )

    def get(self, user_id: str) -> RelationshipState:
        return self.repository.get_or_create(user_id.strip())

    def reset(self, user_id: str) -> RelationshipState:
        return self.repository.reset(user_id.strip())

