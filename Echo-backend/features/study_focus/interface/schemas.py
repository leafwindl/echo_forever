from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StudyFocusCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    activity_type: str = Field(default="学习", min_length=1, max_length=40)
    short_goal: str = Field(default="", max_length=80)
    planned_duration_seconds: int = Field(ge=60, le=10800)
    started_at: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)

    @field_validator("session_id", "activity_type", "timezone")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value is required")
        return value


class StudyFocusUpdateRequest(BaseModel):
    status: Literal["running", "paused", "completed", "ended_early"]
    actual_duration_seconds: int = Field(ge=0, le=10800)
    occurred_at: datetime


class StudyFocusResponse(BaseModel):
    session_id: str
    activity_type: str
    short_goal: str
    planned_duration_seconds: int
    actual_duration_seconds: int
    status: str
    started_at: datetime
    timezone: str
    ended_at: datetime | None = None
    completion_message_id: int | None = None


class StudyFocusListResponse(BaseModel):
    items: list[StudyFocusResponse]
    total_actual_duration_seconds: int
