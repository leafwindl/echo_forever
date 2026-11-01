from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.relationship.domain.entities import RelationshipValidationError
from features.relationship.public import (
    RELATIONSHIP_DIRECTION_LABELS,
    decline_relationship_direction,
    decline_relationship_proposal,
    defer_relationship_proposal,
    get_pending_relationship_proposal,
    propose_relationship,
)


class ProposeRelationshipArguments(BaseModel):
    evidence: str = Field(default="", max_length=300)


class RespondRelationshipArguments(BaseModel):
    action: Literal["decline", "defer"]
    direction: Literal["friend", "ambiguous", "partner"] | None = None
    evidence: str = Field(default="", max_length=300)


def register_relationship_tools(registry: ToolRegistry) -> None:
    async def propose_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = ProposeRelationshipArguments.model_validate(arguments)
        try:
            proposal = propose_relationship(
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
                tool_name="propose_relationship",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="relationship_not_eligible",
            )
        payload = {
            "created": True,
            "proposal_id": proposal.proposal_id,
            "direction": proposal.direction,
            "direction_label": RELATIONSHIP_DIRECTION_LABELS.get(
                proposal.direction, proposal.direction
            ),
            "delivery": "confirmation_window_after_message",
            "relationship_changed": False,
        }
        return AgentToolResult(
            call_id="",
            tool_name="propose_relationship",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def respond_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = RespondRelationshipArguments.model_validate(arguments)
        pending = get_pending_relationship_proposal(context.user_id)
        try:
            if parsed.action == "decline":
                if pending is not None:
                    proposal = decline_relationship_proposal(
                        context.user_id, pending.proposal_id, parsed.evidence
                    )
                    payload = {
                        "resolved": True,
                        "proposal_id": proposal.proposal_id,
                        "direction": proposal.direction,
                        "status": "declined",
                    }
                elif parsed.direction is not None:
                    boundary = decline_relationship_direction(
                        context.user_id, parsed.direction, parsed.evidence
                    )
                    payload = {
                        "resolved": True,
                        "direction": boundary.direction,
                        "status": "declined",
                    }
                else:
                    raise RelationshipValidationError("No pending proposal or direction")
            else:
                if pending is None:
                    raise RelationshipValidationError("No pending proposal")
                proposal = defer_relationship_proposal(
                    context.user_id, pending.proposal_id, parsed.evidence
                )
                payload = {
                    "resolved": True,
                    "proposal_id": proposal.proposal_id,
                    "direction": proposal.direction,
                    "status": "deferred",
                }
        except RelationshipValidationError as exc:
            payload = {"resolved": False, "reason": str(exc)}
            return AgentToolResult(
                call_id="",
                tool_name="respond_relationship",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="relationship_response_not_applicable",
            )
        return AgentToolResult(
            call_id="",
            tool_name="respond_relationship",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="propose_relationship",
                description=(
                    "在用户已经明确表达愿意把关系更进一步后，创建一个关系确认窗口。"
                    "不要替用户决定关系，也不要声称关系已经改变；用户点击确认后才会改变。"
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat",),
            ),
            arguments_model=ProposeRelationshipArguments,
            handler=propose_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="respond_relationship",
                description=(
                    "当用户明确拒绝或想暂缓一段关系推进时，记录这次回应。"
                    "只有用户真的明确表达时才调用；不要为了结束话题而伪造拒绝。"
                ),
                risk_level=ToolRisk.CREATE_INTERNAL,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat",),
            ),
            arguments_model=RespondRelationshipArguments,
            handler=respond_handler,
        )
    )
