from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class PresenceStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    RESTING = "resting"
    SLEEPING = "sleeping"
    FOCUSED = "focused"


@dataclass(frozen=True)
class PresenceState:
    user_id: str
    status: str = PresenceStatus.IDLE
    enabled: bool = True
    last_user_message_at: datetime | None = None
    last_tick_at: datetime | None = None
    next_tick_at: datetime | None = None
    last_thought_at: datetime | None = None
    thought_budget_date: date | None = None
    thoughts_used: int = 0
    last_proactive_message_at: datetime | None = None
    proactive_messages_used: int = 0
    proactive_budget_date: date | None = None
    outreach_sent_count: int = 0
    outreach_replied_count: int = 0
    consecutive_unanswered: int = 0
    outreach_downshift_until: datetime | None = None
    outreach_last_counted_at: datetime | None = None
    proactive_actions_used: int = 0
    proactive_action_budget_date: date | None = None
    last_proactive_action_at: datetime | None = None
    last_decision: str = ""
    last_decision_reason: str = ""
    consecutive_skips: int = 0
    activities_used: int = 0
    activity_budget_date: date | None = None
    last_activity_at: datetime | None = None
    consecutive_l0: int = 0
    l2_used: int = 0
    l2_budget_date: date | None = None


@dataclass(frozen=True)
class AgendaItem:
    item_id: str
    user_id: str
    kind: str
    title: str
    action_kind: str
    status: str = "open"
    created_at: datetime | None = None


@dataclass(frozen=True)
class PresenceThought:
    thought_id: str
    user_id: str
    text: str
    salience: float
    shareable: bool
    action_intent: str = ""
    source_memory_id: str = ""
    source_memory_text: str = ""
    draft_text: str = ""
    plan: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class PresenceMessage:
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class PresenceActionSummary:
    kind: str
    summary: str
    occurred_at: datetime


@dataclass(frozen=True)
class PresenceContext:
    messages: tuple[PresenceMessage, ...]
    last_user_message_at: datetime | None
    last_user_text: str
    recent_assistant_text: str
    last_assistant_at: datetime | None = None
    timezone: str = "Asia/Shanghai"
    recent_actions: tuple[PresenceActionSummary, ...] = ()
    recent_messages: tuple[PresenceMessage, ...] = ()
    open_goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class PresenceMemory:
    memory_id: str
    content: str
    importance: int = 3


@dataclass(frozen=True)
class ThoughtDraft:
    text: str
    salience: float
    shareable: bool = False
    action_intent: str = ""
    action_request: str = ""
    draft_text: str = ""
    plan: str = ""


@dataclass(frozen=True)
class PresenceTickResult:
    user_id: str
    status: str
    decision: str
    reason: str
    thought: PresenceThought | None = None
    message_text: str = ""
    action_result: str = ""
    thoughts_used: int = 0
