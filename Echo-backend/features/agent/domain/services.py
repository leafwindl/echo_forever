from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from features.agent.domain.entities import AgentModelResponse, ProactiveDecision


class AgentModelTimeoutError(TimeoutError):
    """The configured conversation model request timed out."""


class StickerSemanticAnalysisError(ValueError):
    """The model did not return a valid sticker semantic decision."""


class StickerToolPolicy(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class StickerRequestDecision:
    policy: StickerToolPolicy
    intent: str = ""


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


class StickerSemanticAnalyzer(Protocol):
    async def assess_request(
        self,
        message: str,
        messages: list[dict],
    ) -> StickerRequestDecision: ...

    async def claims_sticker_delivery(self, reply_text: str) -> bool: ...


class ProactiveDecisionPlanner(Protocol):
    async def decide(
        self,
        messages: list[dict],
        available_fact_ids: tuple[str, ...],
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
