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


class StageAdvanceResponse(BaseModel):
    request_id: str
    target_stage: str
    target_stage_label: str
    status: str
    created_at: str | None = None
    expires_at: str | None = None
    cooldown_until: str | None = None
