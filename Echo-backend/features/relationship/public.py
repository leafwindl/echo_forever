from features.relationship.application.relationship_management import (
    RelationshipManagementService,
)
from features.relationship.domain.entities import (
    RELATIONSHIP_SCHEMA_VERSION,
    STAGE_LABELS,
    RelationshipContext,
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


__all__ = [
    "RelationshipContext",
    "RelationshipManagementService",
    "RelationshipState",
    "RelationshipValidationError",
    "RELATIONSHIP_SCHEMA_VERSION",
    "STAGE_LABELS",
    "get_relationship_context",
    "get_relationship_state",
    "record_relationship_turn",
    "reset_relationship_state",
]
