from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from features.agent.domain.entities import AgentModelResponse, ProactiveDecision


class AgentModelTimeoutError(TimeoutError):
    """The configured conversation model request timed out."""


class ProactivePlannerError(RuntimeError):
    """The proactive planner failed before making a business decision."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
