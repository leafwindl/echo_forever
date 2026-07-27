from features.persona.application.persona_management import PersonaManagementService
from features.persona.domain.entities import (
    PERSONA_SCHEMA_VERSION,
    PersonaOperationError,
    PersonaUpdate,
    PersonaValidationError,
    UserPreferences,
)
from features.persona.infrastructure.container import get_persona_management_service


def get_persona(user_id: str) -> UserPreferences:
    """稳定模块入口：读取用户显式设置，未设置时返回默认值。"""
    return get_persona_management_service().get(user_id)


def update_persona(user_id: str, update: PersonaUpdate) -> UserPreferences:
    """稳定模块入口：完整替换当前用户的显式设置。"""
    return get_persona_management_service().update(user_id, update)


def reset_persona(user_id: str) -> UserPreferences:
    """稳定模块入口：只恢复 Persona 默认值，不影响记忆和聊天。"""
    return get_persona_management_service().reset(user_id)


__all__ = [
    "PERSONA_SCHEMA_VERSION",
    "PersonaManagementService",
    "PersonaOperationError",
    "PersonaUpdate",
    "PersonaValidationError",
    "UserPreferences",
    "get_persona",
    "reset_persona",
    "update_persona",
]
