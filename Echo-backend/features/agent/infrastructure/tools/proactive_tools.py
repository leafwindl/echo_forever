from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.proactive_chat.public import get_proactive_repository


class PauseProactiveArguments(BaseModel):
    days: int | None = Field(default=None, ge=1, le=30)
    indefinite: bool = False


class ResumeProactiveArguments(BaseModel):
    pass


def register_proactive_tools(registry: ToolRegistry) -> None:
    repository = get_proactive_repository()

    async def pause_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = PauseProactiveArguments.model_validate(arguments)
        until = None
        if not parsed.indefinite:
            days = parsed.days if parsed.days is not None else 2
            until = datetime.now(UTC) + timedelta(days=days)
        preference = repository.pause_spontaneous(
            context.user_id,
            until=until,
            indefinite=parsed.indefinite,
        )
        payload = {
            "paused": True,
            "pause_indefinite": preference.pause_indefinite,
            "paused_until": preference.paused_until.isoformat()
            if preference.paused_until
            else None,
        }
        return AgentToolResult(
            call_id="",
            tool_name="pause_proactive_contact",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def resume_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        ResumeProactiveArguments.model_validate(arguments)
        preference = repository.resume_spontaneous(context.user_id)
        payload = {
            "resumed": True,
            "pause_indefinite": preference.pause_indefinite,
        }
        return AgentToolResult(
            call_id="",
            tool_name="resume_proactive_contact",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="pause_proactive_contact",
                description=(
                    "用户明确要求暂停 Echo 的自然主动联系时调用。"
                    "用户说“这两天别主动找我”用 days；说“以后别主动发消息”用 indefinite。"
                    "明确提醒任务不受影响。"
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat",),
            ),
            arguments_model=PauseProactiveArguments,
            handler=pause_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="resume_proactive_contact",
                description=(
                    "用户明确要求恢复 Echo 的自然主动联系时调用。"
                    "不要因为用户只是聊得开心就自动恢复。"
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat",),
            ),
            arguments_model=ResumeProactiveArguments,
            handler=resume_handler,
        )
    )
