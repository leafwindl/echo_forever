from features.persona.application.persona_management import PersonaManagementService
from features.persona.infrastructure.postgres_repository import PostgresPersonaRepository

_persona_management_service: PersonaManagementService | None = None


def get_persona_management_service() -> PersonaManagementService:
    """集中装配 Persona 仓储，避免应用层依赖数据库实现。"""
    global _persona_management_service
    if _persona_management_service is None:
        _persona_management_service = PersonaManagementService(PostgresPersonaRepository())
    return _persona_management_service


def reset_persona_management_service_for_tests() -> None:
    global _persona_management_service
    _persona_management_service = None
