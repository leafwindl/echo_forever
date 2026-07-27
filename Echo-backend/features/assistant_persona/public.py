from features.assistant_persona.domain.entities import (
    AssistantPersona,
    AssistantPersonaNotFoundError,
)
from features.assistant_persona.infrastructure.default_persona import (
    get_configured_assistant_persona,
)


def get_assistant_persona(version: str) -> AssistantPersona:
    return get_configured_assistant_persona(version)


__all__ = [
    "AssistantPersona",
    "AssistantPersonaNotFoundError",
    "get_assistant_persona",
]
