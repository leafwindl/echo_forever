from typing import Protocol

from features.persona.domain.entities import UserPreferences


class PersonaRepository(Protocol):
    """用户 Persona 的持久化契约。"""

    def get(self, user_id: str) -> UserPreferences | None: ...

    def save(self, preferences: UserPreferences) -> UserPreferences: ...
