from __future__ import annotations

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProactivePreferencesRequest(BaseModel):
    enabled: bool = False
    allow_echo_scheduling: bool = True
    allow_spontaneous_chat: bool = False
    proactivity_level: Literal["conservative", "balanced", "active"] = "balanced"
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    quiet_start: time = time(22, 30)
    quiet_end: time = time(8, 0)
    explicit_reminder_quiet_policy: Literal["honor", "defer"] = "defer"
    notification_preview: bool = False


class ProactivePreferencesResponse(ProactivePreferencesRequest):
    pass


class ChatScheduleCreateRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=500)
    user_visible_label: str = Field(default="", max_length=100)
    local_datetime: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    schedule_type: Literal["once", "daily", "weekly"] = "once"

    @field_validator("intent")
    @classmethod
    def clean_intent(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("intent is required")
        return value


class ChatScheduleUpdateRequest(BaseModel):
    status: Literal["active", "paused", "cancelled"] | None = None
    user_visible_label: str | None = Field(default=None, max_length=100)
    local_datetime: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)


class ChatScheduleResponse(BaseModel):
    schedule_id: str
    created_by: str
    schedule_type: str
    intent: str
    user_visible_label: str
    timezone: str
    next_run_at: datetime
    recurrence_rule: dict[str, object] = Field(default_factory=dict)
    status: str
    run_count: int
    max_runs: int | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChatScheduleListResponse(BaseModel):
    items: list[ChatScheduleResponse] = Field(default_factory=list)
