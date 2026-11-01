from typing import Literal

from pydantic import BaseModel


class RelationshipModeUpdateRequest(BaseModel):
    relationship_mode: Literal["friend", "ai_partner"]


class RelationshipProposalResponse(BaseModel):
    proposal_id: str
    direction: str
    direction_label: str
    status: str
    created_at: str | None = None
    expires_at: str | None = None


class RelationshipResponse(BaseModel):
    relationship_mode: str
    relationship_type: str
    relationship_type_label: str
    stage: str
    stage_label: str
    interaction_turns: int
    active_days: int
    affection_permission: str
    pending_proposal: RelationshipProposalResponse | None = None
    schema_version: int
    created_at: str | None = None
    updated_at: str | None = None
