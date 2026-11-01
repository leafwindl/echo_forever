from __future__ import annotations

import json

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
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
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="emit_chat_beats",
                description=(
                    "文字聊天打算发两条以上消息时，优先调用本工具，一次给出 1-10 条；"
                    "不要用换行直接写多段。每条是一个自然气泡；普通闲聊 2-5 条，"
                    "斗嘴/情绪强时可以 6-10 条，允许“哈哈”这类独立短反应。"
                    "谈心、解释、长回答只给 1 条长文本，不要为了凑气泡把内容拆碎。"
                    "表情包另用 send_sticker，并用 after_text_index 指定夹在第几条文字之后。"
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "proactive"),
            ),
            arguments_model=EmitChatBeatsArguments,
            handler=emit_handler,
        )
    )
