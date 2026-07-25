from typing import Protocol

from features.persona.domain.entities import UserPersona


class PersonaRepository(Protocol):
    """用户 Persona 的持久化契约。"""

    def get(self, user_id: str) -> UserPersona | None: ...

    def save(self, persona: UserPersona) -> UserPersona: ...

    def delete(self, user_id: str) -> bool: ...
