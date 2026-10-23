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
    placement: Literal["before_text", "after_text"] = "after_text"


StickerSearch = Callable[..., list[Sticker] | Awaitable[list[Sticker]]]
StickerSend = Callable[[str, str], Sticker | None]


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
        requested_intent = parsed.intent.strip()
        found = search(context.user_id, requested_intent, 3)
        stickers = await found if inspect.isawaitable(found) else found
        if not stickers:
            payload = {
                "sent": False,
                "status": "no_result",
                "intent": requested_intent,
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
            "placement": parsed.placement,
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
                description="根据想表达的情绪或语境，发送一张可用表情包；未找到则不发送。",
                risk_level=ToolRisk.SEND,
                timeout_seconds=5,
                is_idempotent=True,
                allowed_modes=("chat", "proactive"),
                allow_proactive=True,
            ),
            arguments_model=SendStickerArguments,
            handler=send_handler,
        )
    )
