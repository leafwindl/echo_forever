from __future__ import annotations

import json

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry


class EmitChatBeatsArguments(BaseModel):
    beats: list[str] = Field(min_length=1, max_length=10)


def _clean_beats(raw_beats: list[str]) -> tuple[str, ...]:
    beats: list[str] = []
    seen: set[str] = set()
    for value in raw_beats:
        beat = value.strip()
        if not beat:
            continue
        if len(beat) > 2000:
            raise ValueError("单条气泡过长")
        if beat in seen:
            raise ValueError("气泡内容重复")
        seen.add(beat)
        beats.append(beat)
    if not beats:
        raise ValueError("至少需要一条气泡")
    if len(beats) > 10:
        raise ValueError("最多 10 条气泡")
    return tuple(beats)


def register_beat_tools(registry: ToolRegistry) -> None:
    async def emit_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        del context
        parsed = EmitChatBeatsArguments.model_validate(arguments)
        try:
            beats = _clean_beats(parsed.beats)
        except ValueError as exc:
            payload = {"accepted": False, "reason": str(exc)}
            return AgentToolResult(
                call_id="",
                tool_name="emit_chat_beats",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="invalid_chat_beats",
            )
        payload = {
            "accepted": True,
            "beat_count": len(beats),
            "beats": list(beats),
        }
        return AgentToolResult(
            call_id="",
            tool_name="emit_chat_beats",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
            published_segments=beats,
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="emit_chat_beats",
                description=(
                    "打算连发多条短消息时调用，一次给出 1-10 条气泡；"
                    "深谈和长回答不要用它拆碎。"
                ),
                timeout_seconds=5,
                allowed_modes=("chat", "proactive"),
            ),
            arguments_model=EmitChatBeatsArguments,
            handler=emit_handler,
        )
    )
