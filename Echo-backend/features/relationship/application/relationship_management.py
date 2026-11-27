from datetime import datetime, timedelta, timezone

from features.relationship.domain.affection import (
    stage_for_affection,
    validate_adjustment,
)
from features.relationship.domain.entities import (
    AffectionAdjustment,
    RelationshipContext,
    RelationshipState,
    RelationshipValidationError,
    StageAdvanceRequest,
    default_relationship_state,
)
from features.relationship.domain.repositories import RelationshipRepository
from features.relationship.domain.rules import (
    advance_relationship_state,
    build_relationship_context,
    next_requestable_stage,
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

    def get_context(
        self,
        user_id: str,
        user_message: str,
        relationship_pace: str,
        affection_style: str,
    ) -> RelationshipContext:
        state = self.repository.get_or_create(user_id.strip())
        pending_stage_request = None
        get_pending = getattr(self.repository, "get_pending_stage_request", None)
        if callable(get_pending):
            pending_stage_request = get_pending(state.user_id)
        return build_relationship_context(
            state,
            user_message,
            relationship_pace,
            affection_style,
            stage_asset="unconfirmed" if pending_stage_request is not None else "",
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

    def adjust_affection(
        self,
        *,
        user_id: str,
        delta: int,
        reason: str,
        agent_turn_id: str,
    ) -> AffectionAdjustment:
        clean_user_id = default_relationship_state(user_id).user_id
        clean_delta, clean_reason = validate_adjustment(delta, reason)
        state, applied = self.repository.adjust_affection(
            user_id=clean_user_id,
            delta=clean_delta,
            reason=clean_reason,
            agent_turn_id=agent_turn_id.strip(),
        )
        return AffectionAdjustment(
            delta=applied,
            affection=state.affection,
            affection_stage=stage_for_affection(state.affection),
            stage=state.stage,
        )

    def pending_stage_request(self, user_id: str) -> StageAdvanceRequest | None:
        return self.repository.get_pending_stage_request(user_id.strip())

    def request_stage_advance(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        agent_turn_id: str | None,
        evidence: str,
    ) -> StageAdvanceRequest:
        clean_user_id = default_relationship_state(user_id).user_id
        state = self.repository.get_or_create(clean_user_id)
        target_stage = next_requestable_stage(state.stage, state.affection)
        if not target_stage:
            raise RelationshipValidationError("Stage advance is not eligible")
        pending = self.repository.get_pending_stage_request(clean_user_id)
        if pending is not None:
            raise RelationshipValidationError("Stage request already pending")
        latest = self.repository.latest_stage_request(clean_user_id)
        now = _utc_now()
        if latest is not None and latest.cooldown_until:
            cooldown_until = _parse_timestamp(latest.cooldown_until)
            if cooldown_until is not None and cooldown_until > now:
                raise RelationshipValidationError("Stage request is cooling down")
        return self.repository.create_stage_request(
            user_id=clean_user_id,
            target_stage=target_stage,
            conversation_id=conversation_id,
            agent_turn_id=agent_turn_id,
            evidence=evidence.strip(),
            expires_at=(now + _PROPOSAL_TTL).isoformat(),
        )

    def accept_stage_request(self, user_id: str, request_id: str) -> RelationshipState:
        clean_user_id = default_relationship_state(user_id).user_id
        request = self.repository.get_stage_request(clean_user_id, request_id.strip())
        if request is None or request.status != "pending":
            raise RelationshipValidationError("No pending stage request")
        expires_at = _parse_timestamp(request.expires_at)
        if expires_at is not None and expires_at <= _utc_now():
            raise RelationshipValidationError("Stage request expired")
        return self.repository.accept_stage_request(
            user_id=clean_user_id,
            request_id=request.request_id,
            resolved_at=_utc_now().isoformat(),
        )

    def decline_stage_request(
        self, user_id: str, request_id: str, evidence: str = ""
    ) -> StageAdvanceRequest:
        return self._resolve_stage_request(user_id, request_id, "declined", evidence)

    def defer_stage_request(
        self, user_id: str, request_id: str, evidence: str = ""
    ) -> StageAdvanceRequest:
        return self._resolve_stage_request(user_id, request_id, "deferred", evidence)

    def _resolve_stage_request(
        self, user_id: str, request_id: str, status: str, evidence: str
    ) -> StageAdvanceRequest:
        clean_user_id = default_relationship_state(user_id).user_id
        now = _utc_now()
        return self.repository.resolve_stage_request(
            user_id=clean_user_id,
            request_id=request_id.strip(),
            status=status,
            resolved_at=now.isoformat(),
            cooldown_until=(now + timedelta(days=_DEFER_DAYS)).isoformat(),
        )
