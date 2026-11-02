from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PresenceThoughtResponse(BaseModel):
    thought_id: str
    text: str
    salience: float
    shareable: bool
    action_intent: str = ""
    created_at: datetime


class PresenceResponse(BaseModel):
    status: str
    enabled: bool
    last_user_message_at: datetime | None = None
    last_tick_at: datetime | None = None
    last_thought_at: datetime | None = None
    thoughts_used: int = 0
    daily_thought_budget: int
    last_decision: str = ""
    last_decision_reason: str = ""
    thoughts: list[PresenceThoughtResponse] = Field(default_factory=list)
