from dataclasses import dataclass


RELATIONSHIP_SCHEMA_VERSION = 2
RELATIONSHIP_STAGES = ("new", "familiar", "trusted", "close")
RELATIONSHIP_MODES = ("friend", "ai_partner")
AFFECTION_PERMISSIONS = ("unknown", "restrained", "welcomed")
INTERACTION_WARMTH_LEVELS = ("reserved", "normal", "warm")

STAGE_LABELS = {
    "new": "初识",
    "familiar": "熟悉",
    "trusted": "信赖",
    "close": "亲近",
}


class RelationshipValidationError(ValueError):
    """Raised when relationship state violates domain constraints."""


@dataclass(frozen=True)
class RelationshipSignal:
    event_type: str
    weight: int = 0


@dataclass(frozen=True)
class RelationshipState:
    user_id: str
    stage: str = "new"
    relationship_mode: str = "friend"
    score: int = 0
    interaction_turns: int = 0
    active_days: int = 0
    shared_memory_count: int = 0
    positive_signal_count: int = 0
    explicit_relation_signal_count: int = 0
    boundary_signal_count: int = 0
    affection_permission: str = "unknown"
    last_interaction_date: str | None = None
    last_interaction_at: str | None = None
    last_boundary_at: str | None = None
    stage_updated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    schema_version: int = RELATIONSHIP_SCHEMA_VERSION


@dataclass(frozen=True)
class RelationshipContext:
    state: RelationshipState
    interaction_warmth: str
    effective_affection_style: str


@dataclass(frozen=True)
class RelationshipProgress:
    state: RelationshipState
    signals: tuple[RelationshipSignal, ...]
    stage_changed: bool


def default_relationship_state(user_id: str) -> RelationshipState:
    clean_user_id = user_id.strip()
    if not clean_user_id:
        raise RelationshipValidationError("Missing user_id")
    return RelationshipState(user_id=clean_user_id)

