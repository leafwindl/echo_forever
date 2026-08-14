from __future__ import annotations

import asyncio

from pydantic import ValidationError

from features.agent.domain.entities import (
    AgentToolCall,
    AgentToolResult,
    AgentToolStatus,
)
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        context: ToolExecutionContext,
        call: AgentToolCall,
    ) -> AgentToolResult:
        definition = self.registry.get(call.tool_name)
        if definition is None:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="unknown_tool",
            )
        matching_results = tuple(
            result
            for result in context.prior_results
            if result.tool_name == call.tool_name and result.arguments == call.arguments
        )
        if matching_results:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="duplicate_tool_call",
            )
        if context.conversation_mode not in definition.specification.allowed_modes:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="tool_not_allowed_in_mode",
            )
        successful_call_limit = definition.specification.max_successful_calls_per_turn
        successful_call_count = sum(
            result.tool_name == call.tool_name and result.status == AgentToolStatus.COMPLETED
            for result in context.prior_results
        )
        if successful_call_limit is not None and successful_call_count >= successful_call_limit:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="tool_success_limit",
            )
        previous_call_count = sum(
            result.tool_name == call.tool_name
            and (
                definition.specification.count_no_result_toward_call_limit
                or result.status != AgentToolStatus.NO_RESULT
            )
            for result in context.prior_results
        )
        if previous_call_count >= definition.specification.max_calls_per_turn:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="tool_call_limit",
            )
        try:
            arguments = definition.arguments_model.model_validate(call.arguments)
        except ValidationError:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code="invalid_tool_arguments",
            )
        try:
            result = await asyncio.wait_for(
                definition.handler(context, arguments),
                timeout=definition.specification.timeout_seconds,
            )
        except TimeoutError:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.TIMED_OUT,
                arguments=call.arguments,
                error_code="tool_timeout",
            )
        except Exception as exc:
            return AgentToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=AgentToolStatus.FAILED,
                arguments=call.arguments,
                error_code=type(exc).__name__,
            )
        return AgentToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=result.status,
            arguments=call.arguments,
            data=result.data,
            safe_for_model=result.safe_for_model,
            content_parts=result.content_parts,
            sources=result.sources,
            error_code=result.error_code,
        )
