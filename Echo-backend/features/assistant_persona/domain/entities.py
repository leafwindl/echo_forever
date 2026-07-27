from dataclasses import dataclass


class AssistantPersonaNotFoundError(ValueError):
    """Raised when configuration references an unknown persona version."""


@dataclass(frozen=True)
class AssistantPersona:
    """Product-owned identity and observable behavior contract for Echo."""

    persona_id: str
    version: str
    name: str
    role: str
    traits: tuple[str, ...]
    conversation_principles: tuple[str, ...]
    allowed_self_disclosures: tuple[str, ...]
    forbidden_claims: tuple[str, ...]

