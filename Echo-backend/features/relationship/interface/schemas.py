from typing import Literal

from pydantic import BaseModel


class RelationshipModeUpdateRequest(BaseModel):
    relationship_mode: Literal["friend", "ai_partner"]


class RelationshipResponse(BaseModel):
    relationship_mode: str
    stage: str
    stage_label: str
    interaction_turns: int
    active_days: int
    affection_permission: str
    schema_version: int
    created_at: str | None = None
    updated_at: str | None = None

