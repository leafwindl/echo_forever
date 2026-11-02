from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PairDesktopNodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    name: str = Field(min_length=1, max_length=80)
    fingerprint: str = Field(default="", max_length=128)
    capabilities: list[str] = Field(default_factory=list, max_length=8)


class PairDesktopNodeResponse(BaseModel):
    node_id: str
    user_id: str
    name: str
    token: str
    capabilities: list[str]


class DesktopNodeResponse(BaseModel):
    node_id: str
    name: str
    capabilities: list[str]
    online: bool
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class DesktopNodeListResponse(BaseModel):
    items: list[DesktopNodeResponse]
