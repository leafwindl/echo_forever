from dataclasses import dataclass


RELATIONSHIP_SCHEMA_VERSION = 3
RELATIONSHIP_STAGES = ("new", "familiar", "ambiguous", "lover", "beloved")

STAGE_LABELS = {
    "new": "初识",
    "familiar": "熟悉",
    "ambiguous": "暧昧",
    "lover": "恋人",
    "beloved": "爱人",
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
    reset_epoch: int = 0
    affection: int = 1
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
    stage_asset: str = ""


@dataclass(frozen=True)
class StageAdvanceRequest:
    request_id: str
    user_id: str
    target_stage: str
    status: str
    conversation_id: str | None = None
    agent_turn_id: str | None = None
    evidence: str = ""
    created_at: str | None = None
    resolved_at: str | None = None
    expires_at: str | None = None
    cooldown_until: str | None = None


@dataclass(frozen=True)
class RelationshipProgress:
    state: RelationshipState
    signals: tuple[RelationshipSignal, ...]
    stage_changed: bool


@dataclass(frozen=True)
class AffectionAdjustment:
    delta: int
    affection: int
    affection_stage: str
    stage: str


def default_relationship_state(user_id: str) -> RelationshipState:
    clean_user_id = user_id.strip()
    if not clean_user_id:
        raise RelationshipValidationError("Missing user_id")
    return RelationshipState(user_id=clean_user_id)

