from datetime import datetime, timedelta, timezone

from features.relationship.domain.entities import (
    RELATIONSHIP_DIRECTIONS,
    RELATIONSHIP_MODES,
    RELATIONSHIP_TYPES,
    RelationshipContext,
    RelationshipDirectionBoundary,
    RelationshipProposal,
    RelationshipState,
    RelationshipValidationError,
    default_relationship_state,
)
from features.relationship.domain.repositories import RelationshipRepository
from features.relationship.domain.rules import (
    advance_relationship_state,
    build_relationship_context,
    resolve_proposable_direction,
)

_PROPOSAL_TTL = timedelta(hours=24)
_DEFER_DAYS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class RelationshipManagementService:
    def __init__(self, repository: RelationshipRepository):
        self.repository = repository

    def _active_boundaries(
        self, user_id: str, now: datetime | None = None
    ) -> tuple[RelationshipDirectionBoundary, ...]:
        current = now or _utc_now()
        active: list[RelationshipDirectionBoundary] = []
        for boundary in self.repository.list_direction_boundaries(user_id):
            if boundary.status == "declined":
                active.append(boundary)
                continue
            revisit_after = _parse_timestamp(boundary.revisit_after)
            if revisit_after is None or revisit_after > current:
                active.append(boundary)
        return tuple(active)

    def _blocked_directions(self, user_id: str) -> frozenset[str]:
        return frozenset(boundary.direction for boundary in self._active_boundaries(user_id))

    def get_context(
        self,
        user_id: str,
        user_message: str,
        relationship_pace: str,
        affection_style: str,
    ) -> RelationshipContext:
        state = self.repository.get_or_create(user_id.strip())
        last_interaction = _parse_timestamp(state.last_interaction_at)
        recent_support = (
            last_interaction is not None
            and _utc_now() - last_interaction <= timedelta(days=14)
        )
        return build_relationship_context(
            state,
            user_message,
            relationship_pace,
            affection_style,
            blocked_directions=self._blocked_directions(state.user_id),
            recent_support=recent_support,
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
        now = _utc_now()
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

    def update_mode(self, user_id: str, relationship_mode: str) -> RelationshipState:
        clean_user_id = default_relationship_state(user_id).user_id
        mode = relationship_mode.strip().lower()
        if mode not in RELATIONSHIP_MODES:
            raise RelationshipValidationError("Invalid relationship_mode")
        self.repository.get_or_create(clean_user_id)
        return self.repository.update_mode(clean_user_id, mode)

    def pending_proposal(self, user_id: str) -> RelationshipProposal | None:
        return self.repository.get_pending_proposal(user_id.strip())

    def propose_relationship(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        agent_turn_id: str | None,
        evidence: str,
    ) -> RelationshipProposal:
        clean_user_id = user_id.strip()
        state = self.repository.get_or_create(clean_user_id)
        now = _utc_now()
        pending = self.repository.get_pending_proposal(clean_user_id)
        if pending is not None:
            return pending

        last_interaction = _parse_timestamp(state.last_interaction_at)
        recent_support = (
            last_interaction is not None
            and now - last_interaction <= timedelta(days=14)
        )
        direction = resolve_proposable_direction(
            state,
            blocked_directions=self._blocked_directions(clean_user_id),
            recent_support=recent_support,
        )
        if not direction:
            raise RelationshipValidationError("No relationship direction is eligible")
        return self.repository.create_proposal(
            user_id=clean_user_id,
            direction=direction,
            conversation_id=conversation_id,
            agent_turn_id=agent_turn_id,
            evidence=evidence.strip(),
            expires_at=(now + _PROPOSAL_TTL).isoformat(),
        )

    def accept_proposal(self, user_id: str, proposal_id: str) -> RelationshipState:
        clean_user_id = user_id.strip()
        proposal = self.repository.get_proposal(clean_user_id, proposal_id.strip())
        if proposal is None:
            raise RelationshipValidationError("Proposal not found")
        if proposal.status != "pending":
            raise RelationshipValidationError("Proposal is not pending")
        expires_at = _parse_timestamp(proposal.expires_at)
        if expires_at is not None and expires_at <= _utc_now():
            raise RelationshipValidationError("Proposal expired")
        if proposal.direction not in RELATIONSHIP_TYPES:
            raise RelationshipValidationError("Invalid proposal direction")
        return self.repository.accept_proposal(
            user_id=clean_user_id,
            proposal_id=proposal.proposal_id,
            relationship_type=proposal.direction,
            resolved_at=_utc_now().isoformat(),
        )

    def defer_proposal(
        self, user_id: str, proposal_id: str, evidence: str = ""
    ) -> RelationshipProposal:
        clean_user_id = user_id.strip()
        proposal = self.repository.get_proposal(clean_user_id, proposal_id.strip())
        if proposal is None:
            raise RelationshipValidationError("Proposal not found")
        now = _utc_now()
        resolved = self.repository.resolve_proposal(
            user_id=clean_user_id,
            proposal_id=proposal.proposal_id,
            status="deferred",
            resolved_at=now.isoformat(),
        )
        self.repository.upsert_direction_boundary(
            user_id=clean_user_id,
            direction=proposal.direction,
            status="deferred",
            reason=evidence.strip(),
            source_message_id=proposal.source_message_id,
            revisit_after=(now + timedelta(days=_DEFER_DAYS)).isoformat(),
        )
        return resolved

    def decline_proposal(
        self, user_id: str, proposal_id: str, evidence: str = ""
    ) -> RelationshipProposal:
        clean_user_id = user_id.strip()
        proposal = self.repository.get_proposal(clean_user_id, proposal_id.strip())
        if proposal is None:
            raise RelationshipValidationError("Proposal not found")
        resolved = self.repository.resolve_proposal(
            user_id=clean_user_id,
            proposal_id=proposal.proposal_id,
            status="declined",
            resolved_at=_utc_now().isoformat(),
        )
        self.repository.upsert_direction_boundary(
            user_id=clean_user_id,
            direction=proposal.direction,
            status="declined",
            reason=evidence.strip(),
            source_message_id=proposal.source_message_id,
            revisit_after=None,
        )
        return resolved

    def decline_direction(
        self, user_id: str, direction: str, evidence: str = ""
    ) -> RelationshipDirectionBoundary:
        clean_user_id = user_id.strip()
        clean_direction = direction.strip().lower()
        if clean_direction not in RELATIONSHIP_DIRECTIONS:
            raise RelationshipValidationError("Invalid relationship direction")
        self.repository.cancel_pending_proposals(clean_user_id)
        return self.repository.upsert_direction_boundary(
            user_id=clean_user_id,
            direction=clean_direction,
            status="declined",
            reason=evidence.strip(),
            source_message_id=None,
            revisit_after=None,
        )

    def cancel_pending_proposals(self, user_id: str) -> int:
        return self.repository.cancel_pending_proposals(user_id.strip())
