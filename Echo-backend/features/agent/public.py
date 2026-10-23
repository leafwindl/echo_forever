from collections.abc import Awaitable, Callable

from shared.config import settings

from features.agent.domain.call_routing import route_call_tools
from features.agent.domain.entities import AgentTurnResult, ProactiveDecision
from features.agent.infrastructure.container import (
    get_call_agent,
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
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    on_progress_text: Callable[[str], Awaitable[None]] | None = None,
    tools_enabled: bool | None = None,
) -> AgentTurnResult:
    agent = get_call_agent() if conversation_mode == "call" else get_chat_agent()
    allowed_tool_names: tuple[str, ...] | None = None
    tool_call_limit: int | None = None
    call_route_instruction = ""
    effective_tools_enabled = settings.agent_enabled if tools_enabled is None else tools_enabled
    if conversation_mode == "call":
        call_routing_enabled = (
            settings.call_tool_routing_enabled
            if tools_enabled is None
            else bool(tools_enabled)
        )
        route = route_call_tools(
            message,
            web_search_available=(
                call_routing_enabled
                and settings.call_web_search_enabled
                and settings.web_search_enabled
                and bool(settings.web_search_api_key.strip())
            ),
            schedule_tools_available=(
                call_routing_enabled and settings.call_schedule_tools_enabled
            ),
        )
        allowed_tool_names = route.allowed_tool_names
        tool_call_limit = route.maximum_tool_calls
        call_route_instruction = route.instruction
        effective_tools_enabled = bool(route.allowed_tool_names)
    return await agent.execute(
        user_id,
        message,
        messages,
        conversation_id=conversation_id,
        conversation_mode=conversation_mode,
        sticker_intent=sticker_intent,
        tools_enabled=effective_tools_enabled,
        on_text_delta=on_text_delta,
        on_progress_text=(
            on_progress_text
            if conversation_mode == "call" and settings.call_progress_speech_enabled
            else None
        ),
        allowed_tool_names=allowed_tool_names,
        tool_call_limit=tool_call_limit,
        call_route_instruction=call_route_instruction,
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
    planner_facts: dict[str, object],
    *,
    force_send: bool = False,
) -> ProactiveDecision:
    return await get_proactive_planner().decide(
        planner_facts,
        force_send=force_send,
    )


__all__ = [
    "AgentTurnResult",
    "ProactiveDecision",
    "plan_proactive_message",
    "run_chat_agent",
    "run_daily_letter_agent",
]
