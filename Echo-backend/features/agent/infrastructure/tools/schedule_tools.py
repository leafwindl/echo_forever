from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)


class CreateChatScheduleArguments(BaseModel):
    intent: str = Field(min_length=1, max_length=500)
    schedule_type: Literal["once", "daily", "weekly"] = "once"
    local_datetime: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    user_visible_label: str = Field(default="", max_length=100)


class ListChatSchedulesArguments(BaseModel):
    include_inactive: bool = False


class CancelChatScheduleArguments(BaseModel):
    schedule_id: str = Field(min_length=1, max_length=128)


def _is_explicit_user_request(message: str) -> bool:
    return bool(
        re.search(
            r"提醒(?:我)?|叫我|喊我|设(?:置)?(?:一个)?(?:提醒|闹钟|定时)|"
            r"到时候.{0,6}(?:提醒|问我|叫我)|记得.{0,6}(?:提醒|叫我)",
            message,
        )
    )


def register_schedule_tools(
    registry: ToolRegistry,
    repository: PostgresProactiveChatRepository | None = None,
) -> None:
    schedules = repository or PostgresProactiveChatRepository()

    async def create_handler(
        context: ToolExecutionContext, arguments: BaseModel
    ) -> AgentToolResult:
        parsed = CreateChatScheduleArguments.model_validate(arguments)
        explicit = _is_explicit_user_request(context.trigger_message)
        creator = "user_request" if explicit else "echo_agent"
        preference = schedules.get_preferences(context.user_id)
        if creator == "echo_agent" and (
            not preference.enabled or not preference.allow_echo_scheduling
        ):
            payload = {"created": False, "reason": "echo_scheduling_disabled"}
            return AgentToolResult(
                call_id="",
                tool_name="create_chat_schedule",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="echo_scheduling_disabled",
            )
        if creator == "echo_agent" and parsed.schedule_type != "once":
            payload = {"created": False, "reason": "echo_can_only_create_once"}
            return AgentToolResult(
                call_id="",
                tool_name="create_chat_schedule",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="echo_can_only_create_once",
            )
        try:
            schedule = schedules.create_schedule(
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                created_by=creator,
                schedule_type=parsed.schedule_type,
                intent=parsed.intent,
                user_visible_label=parsed.user_visible_label,
                local_datetime=parsed.local_datetime,
                timezone=parsed.timezone,
            )
        except ValueError as exc:
            payload = {"created": False, "reason": str(exc)}
            return AgentToolResult(
                call_id="",
                tool_name="create_chat_schedule",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="invalid_schedule",
            )
        payload = {
            "created": True,
            "schedule_id": schedule.schedule_id,
            "created_by": schedule.created_by,
            "next_run_at": schedule.next_run_at.isoformat(),
            "timezone": schedule.timezone,
            "label": schedule.user_visible_label,
        }
        return AgentToolResult(
            call_id="",
            tool_name="create_chat_schedule",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def list_handler(context: ToolExecutionContext, arguments: BaseModel) -> AgentToolResult:
        parsed = ListChatSchedulesArguments.model_validate(arguments)
        items = schedules.list_schedules(context.user_id)
        if not parsed.include_inactive:
            items = tuple(item for item in items if item.status in {"active", "paused"})
        payload = {
            "schedules": [
                {
                    "schedule_id": item.schedule_id,
                    "label": item.user_visible_label,
                    "intent": item.intent,
                    "status": item.status,
                    "next_run_at": item.next_run_at.isoformat(),
                    "timezone": item.timezone,
                }
                for item in items[:20]
            ]
        }
        return AgentToolResult(
            call_id="",
            tool_name="list_chat_schedules",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def cancel_handler(
        context: ToolExecutionContext, arguments: BaseModel
    ) -> AgentToolResult:
        parsed = CancelChatScheduleArguments.model_validate(arguments)
        cancelled = schedules.delete_schedule(context.user_id, parsed.schedule_id.strip())
        payload = {"cancelled": cancelled, "schedule_id": parsed.schedule_id.strip()}
        return AgentToolResult(
            call_id="",
            tool_name="cancel_chat_schedule",
            status=AgentToolStatus.COMPLETED if cancelled else AgentToolStatus.NO_RESULT,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="create_chat_schedule",
                description=(
                    "Create a persistent user-visible chat reminder or one-time later "
                    "check-in. Resolve relative time from trusted current-time context; "
                    "when get_current_time is available, use it before creating. "
                    "Use only when a time is clear; ask a concise question when a time "
                    "is ambiguous."
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=False,
                allowed_modes=("chat", "call"),
                max_calls_per_turn=1,
                max_successful_calls_per_turn=1,
            ),
            arguments_model=CreateChatScheduleArguments,
            handler=create_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="list_chat_schedules",
                description=(
                    "List the current user's visible scheduled Echo reminders and follow-ups."
                ),
                risk_level=ToolRisk.READ,
                timeout_seconds=5,
                allowed_modes=("chat", "call"),
                max_calls_per_turn=1,
            ),
            arguments_model=ListChatSchedulesArguments,
            handler=list_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="cancel_chat_schedule",
                description=(
                    "Cancel one visible scheduled Echo reminder by schedule_id returned "
                    "from list_chat_schedules."
                ),
                risk_level=ToolRisk.DESTRUCTIVE,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "call"),
                max_calls_per_turn=1,
            ),
            arguments_model=CancelChatScheduleArguments,
            handler=cancel_handler,
        )
    )
