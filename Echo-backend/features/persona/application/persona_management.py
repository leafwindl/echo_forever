from features.persona.domain.entities import (
    PersonaOperationError,
    PersonaUpdate,
    UserPersona,
    build_user_persona,
    default_user_persona,
)
from features.persona.domain.repositories import PersonaRepository


class PersonaManagementService:
    """管理当前用户的显式偏好，不修改长期记忆或聊天历史。"""

    def __init__(self, repository: PersonaRepository):
        self.repository = repository

    def get(self, user_id: str) -> UserPersona:
        default_persona = default_user_persona(user_id)
        return self.repository.get(default_persona.user_id) or default_persona

    def update(self, user_id: str, update: PersonaUpdate) -> UserPersona:
        persona = build_user_persona(user_id, update, is_customized=True)
        saved_persona = self.repository.save(persona)
        if saved_persona.user_id != persona.user_id:
            raise PersonaOperationError("Failed to save persona")
        return saved_persona

    def reset(self, user_id: str) -> UserPersona:
        persona = default_user_persona(user_id)
        self.repository.delete(persona.user_id)
        return persona
