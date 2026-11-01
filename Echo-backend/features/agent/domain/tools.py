from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from features.agent.domain.entities import (
    AgentToolResult,
    ToolSpecification,
)


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: str
    conversation_id: str | None = None
    conversation_mode: str = "chat"
    trigger_message: str = ""
    agent_turn_id: str = ""
    prior_results: tuple[AgentToolResult, ...] = field(default_factory=tuple)



class ToolArgumentsModel(Protocol):
    """Structural contract for an infrastructure-owned argument validator."""

    @classmethod
    def model_validate(cls, value: Any) -> Any: ...

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]: ...


ToolHandler = Callable[[ToolExecutionContext, Any], Awaitable[AgentToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    specification: ToolSpecification
    arguments_model: type[ToolArgumentsModel]
    handler: ToolHandler

    def model_description(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.specification.name,
                "description": self.specification.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }


class ToolRegistry:
    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        name = definition.specification.name.strip()
        if not name:
            raise ValueError("Tool name cannot be empty")
        if name in self._definitions:
            raise ValueError(f"Tool already registered: {name}")
        self._definitions[name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name.strip())

    def model_descriptions(
        self,
        conversation_mode: str,
        allowed_tool_names: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        allowed_names = (
            {name.strip() for name in allowed_tool_names if name.strip()}
            if allowed_tool_names is not None
            else None
        )
        return tuple(
            definition.model_description()
            for definition in self._definitions.values()
            if conversation_mode in definition.specification.allowed_modes
            and (allowed_names is None or definition.specification.name in allowed_names)
        )
