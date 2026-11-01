from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class ProactiveChatPreferences:
    user_id: str
    enabled: bool
    allow_echo_scheduling: bool
    allow_spontaneous_chat: bool
    timezone: str
    quiet_start: time
    quiet_end: time
    explicit_reminder_quiet_policy: str
    notification_preview: bool
    cycle_started_at: datetime | None = None
    allowed_contact_seconds: int = 0
    last_accounted_at: datetime | None = None
    last_evaluated_slot: int = 0
    last_slot_result: str | None = None
    paused_until: datetime | None = None
    pause_indefinite: bool = False
    last_proactive_at: datetime | None = None
    consecutive_unanswered: int = 0


@dataclass(frozen=True)
class ChatSchedule:
    schedule_id: str
    user_id: str
    conversation_id: str | None
    created_by: str
    schedule_type: str
    intent: str
    user_visible_label: str
    timezone: str
    next_run_at: datetime
    recurrence_rule: dict[str, object]
    status: str
    run_count: int
    max_runs: int | None
    last_run_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProactiveChatJob:
    job_id: str
    schedule_id: str | None
    user_id: str
    conversation_id: str | None
    scheduled_for: datetime
    status: str
    attempt_count: int
    max_attempts: int
