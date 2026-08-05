from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from features.agent.domain.entities import AgentModelResponse


class AgentModelTimeoutError(TimeoutError):
    """The configured conversation model request timed out."""


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
    ) -> AgentModelResponse: ...


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
