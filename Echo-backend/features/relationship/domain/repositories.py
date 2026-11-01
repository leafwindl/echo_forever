from typing import Protocol

from features.relationship.domain.entities import (
    RelationshipDirectionBoundary,
    RelationshipProposal,
    RelationshipSignal,
    RelationshipState,
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

    def update_mode(self, user_id: str, relationship_mode: str) -> RelationshipState: ...

    def update_relationship_type(
        self, user_id: str, relationship_type: str
    ) -> RelationshipState: ...

    def create_proposal(
        self,
        *,
        user_id: str,
        direction: str,
        conversation_id: str | None,
        agent_turn_id: str | None,
        evidence: str,
        expires_at: str,
    ) -> RelationshipProposal: ...

    def get_pending_proposal(self, user_id: str) -> RelationshipProposal | None: ...

    def get_proposal(self, user_id: str, proposal_id: str) -> RelationshipProposal | None: ...

    def accept_proposal(
        self,
        *,
        user_id: str,
        proposal_id: str,
        relationship_type: str,
        resolved_at: str,
    ) -> RelationshipState: ...

    def resolve_proposal(
        self,
        *,
        user_id: str,
        proposal_id: str,
        status: str,
        resolved_at: str,
    ) -> RelationshipProposal: ...

    def list_direction_boundaries(
        self, user_id: str
    ) -> tuple[RelationshipDirectionBoundary, ...]: ...

    def upsert_direction_boundary(
        self,
        *,
        user_id: str,
        direction: str,
        status: str,
        reason: str,
        source_message_id: int | None,
        revisit_after: str | None,
    ) -> RelationshipDirectionBoundary: ...

    def cancel_pending_proposals(self, user_id: str) -> int: ...

