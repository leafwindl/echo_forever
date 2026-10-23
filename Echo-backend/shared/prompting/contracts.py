"""Read-only input contracts consumed by the existing prompt renderer."""

from typing import Protocol


class AssistantPersona(Protocol):
    persona_id: str
    version: str
    name: str
    role: str
    traits: tuple[str, ...]
    conversation_principles: tuple[str, ...]
    allowed_self_disclosures: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    dialogue_examples: tuple[tuple[str, str], ...]


class UserPreferences(Protocol):
    enabled: bool
    preferred_name: str | None
    reply_style: str
    reply_length: str
    support_mode: str
    proactivity: str
    relationship_pace: str
    affection_style: str
    avoid_topics: tuple[str, ...]
    about_user: str | None


class RelationshipState(Protocol):
    stage: str
    relationship_mode: str


class RelationshipContext(Protocol):
    state: RelationshipState
    interaction_warmth: str
    effective_affection_style: str
