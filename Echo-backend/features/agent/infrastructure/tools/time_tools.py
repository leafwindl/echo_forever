from __future__ import annotations

import json

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.services import Clock, resolve_local_time
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry


class GetCurrentTimeArguments(BaseModel):
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    day_offset: int = Field(default=0, ge=-7, le=7)


def register_time_tool(
    registry: ToolRegistry,
    clock: Clock,
    default_timezone: str,
) -> None:
    async def handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        del context
        parsed = GetCurrentTimeArguments.model_validate(arguments)
        timezone_name = parsed.timezone.strip() or default_timezone
        data = resolve_local_time(clock, timezone_name, parsed.day_offset)
        return AgentToolResult(
            call_id="",
            tool_name="get_current_time",
            status=AgentToolStatus.COMPLETED,
            data=data,
            safe_for_model=json.dumps(data, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="get_current_time",
                description=(
                    "获取指定 IANA 时区的可靠日期和时间。回答当前时间、日期、星期或"
                    "相对日期时必须使用此工具，不要依赖模型自身时间。"
                ),
                risk_level=ToolRisk.READ,
                timeout_seconds=3,
                is_idempotent=True,
                max_calls_per_turn=2,
            ),
            arguments_model=GetCurrentTimeArguments,
            handler=handler,
        )
    )
