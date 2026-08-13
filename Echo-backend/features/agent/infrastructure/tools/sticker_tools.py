from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ContentPart,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.stickers.domain.entities import Sticker
from features.stickers.public import search_stickers, send_sticker


class SearchStickersArguments(BaseModel):
    query: str = Field(default="", max_length=300)
    limit: int = Field(default=3, ge=1, le=3)
    purpose: Literal["explicit_request", "proactive"] = "explicit_request"


class SendStickerArguments(BaseModel):
    sticker_id: str = Field(min_length=1, max_length=128)
    purpose: Literal["explicit_request", "proactive"] = "explicit_request"
    placement: Literal["before_text", "after_text"] = "after_text"


StickerSearch = Callable[..., list[Sticker] | Awaitable[list[Sticker]]]
StickerSend = Callable[[str, str], Sticker | None]


async def _search_with_context(
    search: StickerSearch,
    context: ToolExecutionContext,
    query: str,
    limit: int,
    purpose: str,
) -> list[Sticker]:
    try:
        result = search(
            context.user_id,
            query,
            limit,
            conversation_id=context.conversation_id,
            purpose=purpose,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        result = search(context.user_id, query, limit)
    if inspect.isawaitable(result):
        return await result
    return result


def register_sticker_tools(
    registry: ToolRegistry,
    search: StickerSearch = search_stickers,
    send: StickerSend = send_sticker,
) -> None:
    async def search_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = SearchStickersArguments.model_validate(arguments)
        if parsed.purpose == "proactive" and not context.allow_proactive_stickers:
            return AgentToolResult(
                call_id="",
                tool_name="search_stickers",
                status=AgentToolStatus.FAILED,
                data={"purpose": parsed.purpose, "candidates": []},
                safe_for_model='{"status":"blocked","reason":"proactive_sticker_cooldown"}',
                error_code="proactive_sticker_cooldown",
            )
        requested_query = parsed.query.strip()
        stickers = await _search_with_context(
            search,
            context,
            requested_query,
            parsed.limit,
            parsed.purpose,
        )
        fallback_used = False
        if not stickers and parsed.purpose == "explicit_request" and requested_query:
            fallback_used = True
            stickers = await _search_with_context(
                search,
                context,
                "",
                parsed.limit,
                parsed.purpose,
            )
        candidates = [
            {
                "sticker_id": sticker.sticker_id,
                "description": sticker.description,
                "semantic_tags": list(sticker.semantic_tags),
                "priority": sticker.priority,
                "similarity_score": sticker.similarity_score,
            }
            for sticker in stickers
        ]
        status = AgentToolStatus.COMPLETED if candidates else AgentToolStatus.NO_RESULT
        payload = {
            "query": requested_query,
            "purpose": parsed.purpose,
            "fallback_used": fallback_used,
            "candidates": candidates,
        }
        return AgentToolResult(
            call_id="",
            tool_name="search_stickers",
            status=status,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    async def send_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = SendStickerArguments.model_validate(arguments)
        sticker_id = parsed.sticker_id.strip()
        if sticker_id not in context.candidate_sticker_ids:
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data={"sent": False},
                safe_for_model='{"sent": false}',
                error_code="sticker_not_in_search_results",
            )
        if context.sticker_candidate_purpose(sticker_id) != parsed.purpose:
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data={"sent": False},
                safe_for_model='{"sent":false,"reason":"purpose_mismatch"}',
                error_code="sticker_purpose_mismatch",
            )
        if parsed.purpose == "proactive" and not context.allow_proactive_stickers:
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data={"sent": False},
                safe_for_model='{"sent":false,"reason":"proactive_sticker_cooldown"}',
                error_code="proactive_sticker_cooldown",
            )
        sticker = send(context.user_id, sticker_id)
        if sticker is None:
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data={"sent": False},
                safe_for_model='{"sent": false}',
                error_code="sticker_unavailable",
            )
        return AgentToolResult(
            call_id="",
            tool_name="send_sticker",
            status=AgentToolStatus.COMPLETED,
            data={
                "sent": True,
                "delivery": "attached_to_current_reply",
                "purpose": parsed.purpose,
                "placement": parsed.placement,
                "sticker_id": sticker.sticker_id,
                "description": sticker.description,
                "semantic_tags": list(sticker.semantic_tags),
            },
            safe_for_model=json.dumps(
                {
                    "sent": True,
                    "delivery": "attached_to_current_reply",
                    "purpose": parsed.purpose,
                    "placement": parsed.placement,
                    "sticker_id": sticker.sticker_id,
                    "description": sticker.description,
                    "semantic_tags": list(sticker.semantic_tags),
                },
                ensure_ascii=False,
            ),
            content_parts=(
                ContentPart(
                    type="sticker",
                    sticker_id=sticker.sticker_id,
                    url=sticker.url,
                ),
            ),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="search_stickers",
                description=(
                    "根据当前语境中想表达的情绪、态度和使用场景，语义查询当前用户可见的 "
                    "Echo 或私人表情包候选。query 应使用自然语言描述表达意图，不要只堆砌关键词。"
                    "explicit_request 没有语义候选时会回退到其他可用候选。"
                ),
                risk_level=ToolRisk.READ,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=2,
                count_no_result_toward_call_limit=False,
                allow_proactive=True,
            ),
            arguments_model=SearchStickersArguments,
            handler=search_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="send_sticker",
                description="发送本轮 search_stickers 已返回且当前用户可见的一张表情包",
                risk_level=ToolRisk.SEND,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=3,
                max_successful_calls_per_turn=1,
                allow_proactive=True,
            ),
            arguments_model=SendStickerArguments,
            handler=send_handler,
        )
    )
