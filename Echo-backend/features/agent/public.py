import logging
from collections.abc import Awaitable, Callable

from shared.config import settings

from features.agent.application.tool_availability import load_tool_availability
from features.agent.domain.action_registry import (
    ACTION_SPECS,
    ActionSpec,
    actions_for_tier,
    get_action_spec,
    parse_action_kind,
    route_action_request,
)
from features.agent.domain.call_routing import route_call_tools
from features.agent.domain.chat_action_routing import ChatActionMode, route_chat_action
from features.agent.domain.entities import AgentTurnResult, ProactiveDecision
from features.agent.domain.tool_selection import (
    ToolSelectionContext,
    select_chat_tool_names,
    select_proactive_tool_names,
)
from features.agent.infrastructure.container import (
    get_call_agent,
    get_chat_agent,
    get_daily_letter_agent,
    get_proactive_planner,
)

logger = logging.getLogger(__name__)


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
    tool_scope: tuple[str, ...] | None = None,
) -> AgentTurnResult:
    agent = get_call_agent() if conversation_mode == "call" else get_chat_agent()
    allowed_tool_names: tuple[str, ...] | None = None
    tool_call_limit: int | None = None
    call_route_instruction = ""
    action_mode = ChatActionMode.NONE
    require_tool = False
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
    elif conversation_mode in {"chat", "proactive"} and effective_tools_enabled:
        # 设备离线时不宣布对应操作能力，避免模型调用注定失败的设备工具。
        availability = await load_tool_availability(user_id)
        selection_context = ToolSelectionContext(
            conversation_mode=conversation_mode,
            trigger_message=message,
            desktop_online=availability.desktop_online,
            phone_online=availability.phone_online,
            echo_computer_online=availability.echo_computer_online,
        )
        if conversation_mode == "chat":
            allowed_tool_names = select_chat_tool_names(selection_context)
            if (
                settings.chat_action_routing_enabled
                and availability.echo_computer_online
                and allowed_tool_names is not None
            ):
                route = route_chat_action(message)
                if (
                    route.mode is ChatActionMode.NONE
                    and settings.chat_action_intent_enabled
                ):
                    from features.agent.infrastructure.chat_action_intent import (
                        classify_chat_action,
                    )

                    route = await classify_chat_action(message)
                if route.mode is not ChatActionMode.NONE:
                    available = set(allowed_tool_names)
                    routed = tuple(
                        name for name in route.allowed_tool_names if name in available
                    )
                    if routed:
                        allowed_tool_names = routed
                        action_mode = route.mode
                        require_tool = route.require_tool
                        call_route_instruction = route.instruction
        else:
            allowed_tool_names = select_proactive_tool_names(selection_context)
        if tool_scope is not None:
            scope = set(tool_scope)
            allowed_tool_names = tuple(
                name for name in (allowed_tool_names or ()) if name in scope
            )
        computer_tool_count = sum(
            1 for name in (allowed_tool_names or ()) if name.startswith("computer_")
        )
        logger.info(
            "Agent tool selection mode=%s desktop=%s phone=%s echo_computer=%s "
            "tools=%d computer=%d action=%s require_tool=%s",
            conversation_mode,
            availability.desktop_online,
            availability.phone_online,
            availability.echo_computer_online,
            len(allowed_tool_names or ()),
            computer_tool_count,
            action_mode.value,
            require_tool,
        )
    result = await agent.execute(
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
        require_tool=require_tool,
    )
    if action_mode is not ChatActionMode.NONE:
        logger.info(
            "Agent action route result mode=%s tool_calls=%d",
            action_mode.value,
            len(result.tool_results),
        )
    return result


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
    "ACTION_SPECS",
    "ActionSpec",
    "AgentTurnResult",
    "ProactiveDecision",
    "actions_for_tier",
    "get_action_spec",
    "parse_action_kind",
    "route_action_request",
    "plan_proactive_message",
    "run_chat_agent",
    "run_daily_letter_agent",
]
