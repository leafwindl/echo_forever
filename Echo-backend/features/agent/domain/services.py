from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from features.agent.domain.entities import AgentModelResponse, ProactiveDecision


class AgentModelTimeoutError(TimeoutError):
    """The configured conversation model request timed out."""


class ProactivePlannerError(RuntimeError):
    """The proactive planner failed before making a business decision."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()


class AgentConversationModel(Protocol):
    async def complete(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        *,
        structured_output: bool = False,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AgentModelResponse: ...

    async def stream_complete(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        *,
        structured_output: bool = False,
        tool_choice: str | dict[str, Any] = "auto",
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentModelResponse: ...


class ProactiveDecisionPlanner(Protocol):
    async def decide(
        self,
        planner_facts: dict[str, object],
        *,
        force_send: bool = False,
    ) -> ProactiveDecision: ...


def resolve_local_time(clock: Clock, timezone_name: str, day_offset: int = 0) -> dict[str, str]:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone") from exc
    local = clock.now().astimezone(zone) + timedelta(days=day_offset)
    return {
        "local_datetime": local.isoformat(),
        "local_date": local.date().isoformat(),
        "weekday": local.strftime("%A"),
        "utc_offset": local.strftime("%z"),
        "timezone": timezone_name,
    }
