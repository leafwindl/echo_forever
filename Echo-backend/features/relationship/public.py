from features.relationship.application.relationship_management import (
    RelationshipManagementService,
)
from features.relationship.domain.entities import (
    RELATIONSHIP_SCHEMA_VERSION,
    STAGE_LABELS,
    AffectionAdjustment,
    RelationshipContext,
    RelationshipState,
    RelationshipValidationError,
    StageAdvanceRequest,
)
from features.relationship.infrastructure.container import (
    get_relationship_management_service,
)


def get_relationship_context(
    user_id: str,
    user_message: str,
    relationship_pace: str,
    affection_style: str,
) -> RelationshipContext:
    return get_relationship_management_service().get_context(
        user_id,
        user_message,
        relationship_pace,
        affection_style,
    )


def record_relationship_turn(
    user_id: str,
    user_message: str,
    source_message_id: int | None,
    relationship_pace: str,
) -> RelationshipState:
    return get_relationship_management_service().record_turn(
        user_id,
        user_message,
        source_message_id,
        relationship_pace,
    )


def get_relationship_state(user_id: str) -> RelationshipState:
    return get_relationship_management_service().get(user_id)


def reset_relationship_state(user_id: str) -> RelationshipState:
    return get_relationship_management_service().reset(user_id)


def adjust_affection(
    *,
    user_id: str,
    delta: int,
    reason: str,
    agent_turn_id: str,
) -> AffectionAdjustment:
    return get_relationship_management_service().adjust_affection(
        user_id=user_id,
        delta=delta,
        reason=reason,
        agent_turn_id=agent_turn_id,
    )


def get_pending_stage_request(user_id: str) -> StageAdvanceRequest | None:
    return get_relationship_management_service().pending_stage_request(user_id)


def request_stage_advance(
    *,
    user_id: str,
    conversation_id: str | None,
    agent_turn_id: str | None,
    evidence: str,
) -> StageAdvanceRequest:
    return get_relationship_management_service().request_stage_advance(
        user_id=user_id,
        conversation_id=conversation_id,
        agent_turn_id=agent_turn_id,
        evidence=evidence,
    )


def accept_stage_request(user_id: str, request_id: str) -> RelationshipState:
    return get_relationship_management_service().accept_stage_request(user_id, request_id)


def decline_stage_request(
    user_id: str, request_id: str, evidence: str = ""
) -> StageAdvanceRequest:
    return get_relationship_management_service().decline_stage_request(
        user_id, request_id, evidence
    )


def defer_stage_request(
    user_id: str, request_id: str, evidence: str = ""
) -> StageAdvanceRequest:
    return get_relationship_management_service().defer_stage_request(
        user_id, request_id, evidence
    )


__all__ = [
    "AffectionAdjustment",
    "RELATIONSHIP_SCHEMA_VERSION",
    "RelationshipContext",
    "RelationshipManagementService",
    "RelationshipState",
    "RelationshipValidationError",
    "STAGE_LABELS",
    "StageAdvanceRequest",
    "accept_stage_request",
    "adjust_affection",
    "decline_stage_request",
    "defer_stage_request",
    "get_pending_stage_request",
    "get_relationship_context",
    "get_relationship_state",
    "record_relationship_turn",
    "request_stage_advance",
    "reset_relationship_state",
]
