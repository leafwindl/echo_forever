from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StudyFocusSession:
    session_id: str
    user_id: str
    activity_type: str
    short_goal: str
    planned_duration_seconds: int
    actual_duration_seconds: int
    status: str
    started_at: datetime
    timezone: str
    ended_at: datetime | None = None
    completion_message_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
