from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user

from features.presence.interface.schemas import (
    PresenceResponse,
    PresenceThoughtResponse,
)
from features.presence.public import get_presence_state, list_presence_thoughts

router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("/me", response_model=PresenceResponse)
def get_my_presence(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    thought_limit: int = Query(default=10, ge=1, le=30),
):
    state = get_presence_state(current_user.user_id)
    thoughts = list_presence_thoughts(current_user.user_id, thought_limit)
    return PresenceResponse(
        status=state.status,
        enabled=state.enabled,
        last_user_message_at=state.last_user_message_at,
        last_tick_at=state.last_tick_at,
        last_thought_at=state.last_thought_at,
        thoughts_used=state.thoughts_used,
        daily_thought_budget=settings.presence_daily_thought_budget,
        last_decision=state.last_decision,
        last_decision_reason=state.last_decision_reason,
        outreach_sent_count=state.outreach_sent_count,
        outreach_replied_count=state.outreach_replied_count,
        consecutive_unanswered=state.consecutive_unanswered,
        outreach_downshift_until=state.outreach_downshift_until,
        response_rate=(
            state.outreach_replied_count / state.outreach_sent_count
            if state.outreach_sent_count
            else 0.0
        ),
        thoughts=[
            PresenceThoughtResponse(
                thought_id=item.thought_id,
                text=item.text,
                salience=item.salience,
                shareable=item.shareable,
                action_intent=item.action_intent,
                created_at=item.created_at,
            )
            for item in thoughts
            if item.created_at is not None
        ],
    )
