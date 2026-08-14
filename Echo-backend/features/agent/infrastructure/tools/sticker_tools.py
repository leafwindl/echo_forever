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


class SendStickerArguments(BaseModel):
    intent: str = Field(min_length=1, max_length=300)
    purpose: Literal["explicit_request", "proactive"] = "explicit_request"
    placement: Literal["before_text", "after_text"] = "after_text"


StickerSearch = Callable[..., list[Sticker] | Awaitable[list[Sticker]]]
StickerSend = Callable[[str, str], Sticker | None]


async def _search_with_context(
    search: StickerSearch,
    context: ToolExecutionContext,
    intent: str,
    limit: int,
    purpose: str,
) -> list[Sticker]:
    try:
        result = search(
            context.user_id,
            intent,
            limit,
            conversation_id=context.conversation_id,
            purpose=purpose,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        result = search(context.user_id, intent, limit)
    if inspect.isawaitable(result):
        return await result
    return result


def register_sticker_tools(
    registry: ToolRegistry,
    search: StickerSearch = search_stickers,
    send: StickerSend = send_sticker,
) -> None:
    async def send_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = SendStickerArguments.model_validate(arguments)
        if parsed.purpose == "proactive" and not context.allow_proactive_stickers:
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data={"sent": False, "purpose": parsed.purpose},
                safe_for_model='{"sent":false,"reason":"proactive_sticker_cooldown"}',
                error_code="proactive_sticker_cooldown",
            )

        requested_intent = parsed.intent.strip()
        stickers = await _search_with_context(
            search,
            context,
            requested_intent,
            3,
            parsed.purpose,
        )
        fallback_used = False
        if not stickers and parsed.purpose == "explicit_request" and requested_intent:
            fallback_used = True
            stickers = await _search_with_context(
                search,
                context,
                "",
                3,
                parsed.purpose,
            )
        if not stickers:
            payload = {
                "sent": False,
                "status": "no_result",
                "intent": requested_intent,
                "purpose": parsed.purpose,
                "fallback_used": fallback_used,
            }
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.NO_RESULT,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
            )

        selected = stickers[0]
        sticker = send(context.user_id, selected.sticker_id)
        if sticker is None:
            payload = {
                "sent": False,
                "status": "unavailable",
                "intent": requested_intent,
                "purpose": parsed.purpose,
                "fallback_used": fallback_used,
                "sticker_id": selected.sticker_id,
            }
            return AgentToolResult(
                call_id="",
                tool_name="send_sticker",
                status=AgentToolStatus.FAILED,
                data=payload,
                safe_for_model=json.dumps(payload, ensure_ascii=False),
                error_code="sticker_unavailable",
            )

        payload = {
            "sent": True,
            "status": "sent",
            "delivery": "attached_to_current_reply",
            "intent": requested_intent,
            "purpose": parsed.purpose,
            "placement": parsed.placement,
            "fallback_used": fallback_used,
            "sticker_id": sticker.sticker_id,
            "description": sticker.description,
            "semantic_tags": list(sticker.semantic_tags),
        }
        return AgentToolResult(
            call_id="",
            tool_name="send_sticker",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
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
                name="send_sticker",
                description=(
                    "根据自然语言 intent 在当前用户可见的 Echo 官方和私人表情包中进行语义"
                    "搜索、排序、冷却过滤并发送最高优先级的一张。explicit_request 搜索无精确"
                    "结果时会回退到当前可用表情包；没有任何候选时返回 no_result 且不发送。"
                ),
                risk_level=ToolRisk.SEND,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=3,
                max_successful_calls_per_turn=1,
                count_no_result_toward_call_limit=False,
                allow_proactive=True,
            ),
            arguments_model=SendStickerArguments,
            handler=send_handler,
        )
    )
