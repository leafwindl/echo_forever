from collections.abc import Awaitable, Callable

from shared.config import settings

from features.agent.domain.entities import AgentTurnResult, ProactiveDecision
from features.agent.infrastructure.container import (
    get_chat_agent,
    get_daily_letter_agent,
    get_proactive_planner,
)


async def run_chat_agent(
    user_id: str,
    message: str,
    messages: list[dict],
    conversation_id: str | None = None,
    conversation_mode: str = "chat",
    sticker_intent: str = "",
    allow_proactive_stickers: bool = True,
    proactive_sticker_due: bool = False,
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
) -> AgentTurnResult:
    return await get_chat_agent().execute(
        user_id,
        message,
        messages,
        conversation_id=conversation_id,
        conversation_mode=conversation_mode,
        sticker_intent=sticker_intent,
        allow_proactive_stickers=allow_proactive_stickers,
        proactive_sticker_due=proactive_sticker_due,
        tools_enabled=settings.agent_enabled,
        on_text_delta=on_text_delta,
    )


async def run_daily_letter_agent(
    user_id: str,
    objective: str,
    messages: list[dict],
) -> AgentTurnResult:
    """Run the shared Agent core with the restricted daily-letter policy."""
    return await get_daily_letter_agent().execute(
        user_id,
        objective,
        messages,
        conversation_mode="daily_letter",
        tools_enabled=False,
    )


async def plan_proactive_message(
    messages: list[dict],
    available_fact_ids: tuple[str, ...],
    *,
    force_send: bool = False,
) -> ProactiveDecision:
    return await get_proactive_planner().decide(
        messages,
        available_fact_ids,
        force_send=force_send,
    )


__all__ = [
    "AgentTurnResult",
    "ProactiveDecision",
    "plan_proactive_message",
    "run_chat_agent",
    "run_daily_letter_agent",
]
