from pydantic import BaseModel


class RelationshipResponse(BaseModel):
    stage: str
    stage_label: str
    interaction_turns: int
    active_days: int
    affection_permission: str
    schema_version: int
    created_at: str | None = None
    updated_at: str | None = None

