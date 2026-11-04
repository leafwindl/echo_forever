from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class PairMobileAgentRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    name: str = Field(default="", max_length=80)


class MobileAgentDeviceResponse(BaseModel):
    device_id: str
    name: str
    status: str
    online: bool
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class PairMobileAgentResponse(BaseModel):
    device: MobileAgentDeviceResponse
    token: str


class MobileAgentDeviceListResponse(BaseModel):
    items: list[MobileAgentDeviceResponse]


class MobileAgentCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)


class MobileAgentCommandResponse(BaseModel):
    command_id: str
    device_id: str
    data: dict[str, Any]


class MobileAgentAuditItem(BaseModel):
    action_id: str
    device_id: str
    action: str
    status: str
    error_code: str | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class MobileAgentAuditResponse(BaseModel):
    items: list[MobileAgentAuditItem]


class AppSkillRequest(BaseModel):
    query: str = Field(default="", max_length=100)
    device_id: str = Field(default="", max_length=100)
    count: int = Field(default=3, ge=1, le=10)


class AppSkillResponse(BaseModel):
    skill: str
    device_id: str
    action: str
    data: dict[str, Any]
