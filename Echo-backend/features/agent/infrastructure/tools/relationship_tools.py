from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.relationship.domain.entities import RelationshipValidationError
from features.relationship.public import (
    STAGE_LABELS,
    adjust_affection,
    decline_stage_request,
    defer_stage_request,
    get_pending_stage_request,
    request_stage_advance,
)


class AdjustAffectionArguments(BaseModel):
    delta: int = Field(ge=-10, le=10)
    reason: str = Field(min_length=1, max_length=120)


class RequestStageAdvanceArguments(BaseModel):
    evidence: str = Field(default="", max_length=300)


class RespondStageAdvanceArguments(BaseModel):
    action: Literal["decline", "defer"]
    evidence: str = Field(default="", max_length=300)


def register_relationship_tools(registry: ToolRegistry) -> None:
    async def adjust_affection_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = AdjustAffectionArguments.model_validate(arguments)
        try:
            result = adjust_affection(
                user_id=context.user_id,
                delta=parsed.delta,
                reason=parsed.reason,
                agent_turn_id=context.agent_turn_id,
            )
        except ValueError as exc:
            payload = {"applied": False, "reason": str(exc)}
            return AgentToolResult(
                call_id="",
                tool_name="adjust_affection",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="affection_adjustment_rejected",
            )
        payload = {
            "applied": result.delta != 0,
            "delta": result.delta,
            "affection": result.affection,
            "affection_stage": result.affection_stage,
            "stage": result.stage,
        }
        return AgentToolResult(
            call_id="",
            tool_name="adjust_affection",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="adjust_affection",
                description=(
                    "根据本轮互动对 Echo 的好感做一次小幅调整（-10..+10）。"
                    "没有明显正/负向时不要调用；用户拒绝关系推进不扣分。"
                    "同一轮最多一次，不向用户播报精确分数。"
                ),
                timeout_seconds=5,
                allowed_modes=("chat",),
                max_calls_per_turn=1,
            ),
            arguments_model=AdjustAffectionArguments,
            handler=adjust_affection_handler,
        )
    )
    async def request_stage_advance_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = RequestStageAdvanceArguments.model_validate(arguments)
        try:
            request = request_stage_advance(
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                agent_turn_id=context.agent_turn_id or None,
                evidence=parsed.evidence,
            )
        except RelationshipValidationError as exc:
            payload = {
                "created": False,
                "reason": str(exc),
                "relationship_changed": False,
            }
            return AgentToolResult(
                call_id="",
                tool_name="request_stage_advance",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="stage_request_not_eligible",
            )
        payload = {
            "created": True,
            "request_id": request.request_id,
            "target_stage": request.target_stage,
            "target_stage_label": STAGE_LABELS.get(
                request.target_stage, request.target_stage
            ),
            "delivery": "confirmation_window_after_message",
            "relationship_changed": False,
        }
        return AgentToolResult(
            call_id="",
            tool_name="request_stage_advance",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def respond_stage_advance_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = RespondStageAdvanceArguments.model_validate(arguments)
        pending = get_pending_stage_request(context.user_id)
        if pending is None:
            payload = {"resolved": False, "reason": "No pending stage request"}
            return AgentToolResult(
                call_id="",
                tool_name="respond_stage_advance",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="stage_response_not_applicable",
            )
        try:
            if parsed.action == "decline":
                request = decline_stage_request(
                    context.user_id, pending.request_id, parsed.evidence
                )
            else:
                request = defer_stage_request(
                    context.user_id, pending.request_id, parsed.evidence
                )
        except RelationshipValidationError as exc:
            payload = {"resolved": False, "reason": str(exc)}
            return AgentToolResult(
                call_id="",
                tool_name="respond_stage_advance",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="stage_response_not_applicable",
            )
        payload = {
            "resolved": True,
            "request_id": request.request_id,
            "target_stage": request.target_stage,
            "status": request.status,
            "cooldown_until": request.cooldown_until,
        }
        return AgentToolResult(
            call_id="",
            tool_name="respond_stage_advance",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="request_stage_advance",
                description=(
                    "好感达到下一阶段、且用户已经表现出愿意更进一步时，发起阶段请求。"
                    "用户确认前不得声称关系已改变；初识→熟悉不需要请求。"
                ),
                timeout_seconds=5,
                allowed_modes=("chat",),
                max_calls_per_turn=1,
            ),
            arguments_model=RequestStageAdvanceArguments,
            handler=request_stage_advance_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="respond_stage_advance",
                description=(
                    "用户明确拒绝或想暂缓关系阶段推进时，记录这次回应并进入 7 天冷却。"
                    "只有用户真的表达时才调用；不要替用户拒绝。"
                ),
                timeout_seconds=5,
                allowed_modes=("chat",),
                max_calls_per_turn=1,
            ),
            arguments_model=RespondStageAdvanceArguments,
            handler=respond_stage_advance_handler,
        )
    )
