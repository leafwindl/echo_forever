from features.persona.domain.entities import (
    PersonaOperationError,
    PersonaUpdate,
    PersonaValidationError,
    UserPreferences,
    build_user_preferences,
    default_user_preferences,
)
from features.persona.domain.repositories import PersonaRepository


class PersonaManagementService:
    """管理当前用户的显式偏好，不修改长期记忆或聊天历史。"""

    def __init__(self, repository: PersonaRepository):
        self.repository = repository

    def get(self, user_id: str) -> UserPreferences:
        defaults = default_user_preferences(user_id)
        return self.repository.get(defaults.user_id) or defaults

    def update(self, user_id: str, update: PersonaUpdate) -> UserPreferences:
        preferences = build_user_preferences(
            user_id,
            update,
            is_customized=True,
            onboarding_completed=True,
        )
        existing_preferences = self.repository.get(preferences.user_id)
        onboarding_required = (
            existing_preferences is None or not existing_preferences.onboarding_completed
        )
        if onboarding_required and not preferences.preferred_name:
            raise PersonaValidationError("请先填写希望 Echo 使用的称呼")
        saved_preferences = self.repository.save(preferences)
        if saved_preferences.user_id != preferences.user_id:
            raise PersonaOperationError("Failed to save persona")
        return saved_preferences

    def reset(self, user_id: str) -> UserPreferences:
        existing_preferences = self.repository.get(user_id.strip())
        preferences = build_user_preferences(
            user_id,
            PersonaUpdate(),
            is_customized=False,
            onboarding_completed=bool(
                existing_preferences and existing_preferences.onboarding_completed
            ),
        )
        return self.repository.save(preferences)
