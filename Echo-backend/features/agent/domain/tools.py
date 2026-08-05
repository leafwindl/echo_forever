from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from features.agent.domain.entities import (
    AgentToolResult,
    ToolSpecification,
)


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: str
    conversation_mode: str = "chat"
    allow_proactive_stickers: bool = True
    prior_results: tuple[AgentToolResult, ...] = field(default_factory=tuple)

    @property
    def candidate_sticker_ids(self) -> frozenset[str]:
        return frozenset(
            str(candidate.get("sticker_id", ""))
            for result in self.prior_results
            if result.tool_name == "search_stickers"
            for candidate in result.data.get("candidates", [])
            if candidate.get("sticker_id")
        )

    def sticker_candidate_purpose(self, sticker_id: str) -> str:
        for result in reversed(self.prior_results):
            if result.tool_name != "search_stickers":
                continue
            if any(
                str(candidate.get("sticker_id", "")) == sticker_id
                for candidate in result.data.get("candidates", [])
            ):
                return str(result.data.get("purpose", ""))
        return ""


ToolHandler = Callable[[ToolExecutionContext, BaseModel], Awaitable[AgentToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    specification: ToolSpecification
    arguments_model: type[BaseModel]
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

    def model_descriptions(self, conversation_mode: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            definition.model_description()
            for definition in self._definitions.values()
            if conversation_mode in definition.specification.allowed_modes
        )
