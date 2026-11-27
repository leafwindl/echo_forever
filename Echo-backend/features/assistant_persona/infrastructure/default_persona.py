from features.assistant_persona.domain.entities import AssistantPersona
from features.assistant_persona.infrastructure.persona_loader import load_echo_persona


def get_configured_assistant_persona(version: str) -> AssistantPersona:
    return load_echo_persona(version)
