from features.relationship.application.relationship_management import (
    RelationshipManagementService,
)
from features.relationship.infrastructure.postgres_repository import (
    PostgresRelationshipRepository,
)

_relationship_service: RelationshipManagementService | None = None


def get_relationship_management_service() -> RelationshipManagementService:
    global _relationship_service
    if _relationship_service is None:
        _relationship_service = RelationshipManagementService(PostgresRelationshipRepository())
    return _relationship_service


def reset_relationship_management_service_for_tests() -> None:
    global _relationship_service
    _relationship_service = None

