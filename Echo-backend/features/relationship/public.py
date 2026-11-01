from features.relationship.application.relationship_management import (
    RelationshipManagementService,
)
from features.relationship.domain.entities import (
    RELATIONSHIP_DIRECTION_LABELS,
    RELATIONSHIP_SCHEMA_VERSION,
    RELATIONSHIP_TYPE_LABELS,
    STAGE_LABELS,
    RelationshipContext,
    RelationshipDirectionBoundary,
    RelationshipProposal,
    RelationshipState,
    RelationshipValidationError,
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


def update_relationship_mode(user_id: str, relationship_mode: str) -> RelationshipState:
    return get_relationship_management_service().update_mode(user_id, relationship_mode)


def get_pending_relationship_proposal(user_id: str) -> RelationshipProposal | None:
    return get_relationship_management_service().pending_proposal(user_id)


def propose_relationship(
    *,
    user_id: str,
    conversation_id: str | None,
    agent_turn_id: str | None,
    evidence: str,
) -> RelationshipProposal:
    return get_relationship_management_service().propose_relationship(
        user_id=user_id,
        conversation_id=conversation_id,
        agent_turn_id=agent_turn_id,
        evidence=evidence,
    )


def accept_relationship_proposal(user_id: str, proposal_id: str) -> RelationshipState:
    return get_relationship_management_service().accept_proposal(user_id, proposal_id)


def defer_relationship_proposal(
    user_id: str, proposal_id: str, evidence: str = ""
) -> RelationshipProposal:
    return get_relationship_management_service().defer_proposal(
        user_id, proposal_id, evidence
    )


def decline_relationship_proposal(
    user_id: str, proposal_id: str, evidence: str = ""
) -> RelationshipProposal:
    return get_relationship_management_service().decline_proposal(
        user_id, proposal_id, evidence
    )


def decline_relationship_direction(
    user_id: str, direction: str, evidence: str = ""
) -> RelationshipDirectionBoundary:
    return get_relationship_management_service().decline_direction(
        user_id, direction, evidence
    )


__all__ = [
    "update_relationship_mode",
    "RelationshipContext",
    "RelationshipDirectionBoundary",
    "RelationshipManagementService",
    "RelationshipProposal",
    "RelationshipState",
    "RelationshipValidationError",
    "RELATIONSHIP_DIRECTION_LABELS",
    "RELATIONSHIP_SCHEMA_VERSION",
    "RELATIONSHIP_TYPE_LABELS",
    "STAGE_LABELS",
    "accept_relationship_proposal",
    "decline_relationship_direction",
    "decline_relationship_proposal",
    "defer_relationship_proposal",
    "get_pending_relationship_proposal",
    "get_relationship_context",
    "get_relationship_state",
    "propose_relationship",
    "record_relationship_turn",
    "reset_relationship_state",
]
