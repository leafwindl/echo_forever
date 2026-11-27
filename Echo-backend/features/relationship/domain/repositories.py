from datetime import datetime
from typing import Protocol

from features.relationship.domain.entities import (
    RelationshipSignal,
    RelationshipState,
    StageAdvanceRequest,
)


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

    def adjust_affection(
        self,
        *,
        user_id: str,
        delta: int,
        reason: str,
        agent_turn_id: str,
        observed_at: datetime | None = None,
    ) -> tuple[RelationshipState, int]: ...

    def create_stage_request(
        self,
        *,
        user_id: str,
        target_stage: str,
        conversation_id: str | None,
        agent_turn_id: str | None,
        evidence: str,
        expires_at: str,
    ) -> StageAdvanceRequest: ...

    def get_pending_stage_request(self, user_id: str) -> StageAdvanceRequest | None: ...

    def get_stage_request(
        self, user_id: str, request_id: str
    ) -> StageAdvanceRequest | None: ...

    def latest_stage_request(self, user_id: str) -> StageAdvanceRequest | None: ...

    def accept_stage_request(
        self, *, user_id: str, request_id: str, resolved_at: str
    ) -> RelationshipState: ...

    def resolve_stage_request(
        self,
        *,
        user_id: str,
        request_id: str,
        status: str,
        resolved_at: str,
        cooldown_until: str | None,
    ) -> StageAdvanceRequest: ...
