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


_STICKER_FALLBACK_KEYWORDS = (
    "开心",
    "高兴",
    "得意",
    "嘿嘿",
    "调皮",
    "害羞",
    "加油",
    "鼓励",
    "安慰",
    "抱抱",
    "难过",
    "委屈",
    "生气",
    "疑惑",
    "无语",
    "震惊",
    "期待",
    "收到",
    "谢谢",
    "厉害",
    "可爱",
    "尴尬",
    "累",
    "摸鱼",
    "吃瓜",
    "服了",
    "早安",
    "晚安",
    "我来了",
)


def _sticker_search_terms(intent: str) -> tuple[str, ...]:
    terms = [keyword for keyword in _STICKER_FALLBACK_KEYWORDS if keyword in intent]
    terms.append(intent)
    return tuple(dict.fromkeys(term for term in terms if term.strip()))


class SendStickerArguments(BaseModel):
    intent: str = Field(min_length=1, max_length=300)
    placement: Literal["before_text", "after_text"] = "after_text"
    after_text_index: int | None = Field(default=None, ge=0, le=9)


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
        matched_intent = requested_intent
        stickers = []
        for term in _sticker_search_terms(requested_intent):
            found = search(context.user_id, term, 3)
            stickers = await found if inspect.isawaitable(found) else found
            if stickers:
                matched_intent = term
                break
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
            "matched_intent": matched_intent,
            "placement": parsed.placement,
            "after_text_index": parsed.after_text_index,
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
                    after_text_index=(
                        parsed.after_text_index
                        if parsed.after_text_index is not None
                        else -1
                    ),
                ),
            ),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="send_sticker",
                description=(
                    "根据想表达的情绪或语境，发送一张可用表情包；未找到则不发送。"
                    "如果本轮用 emit_chat_beats 发了多条文字，先判断表情回应的是哪一句，"
                    "再用 after_text_index 指定夹在第几条（从 0 开始）之后；不要默认固定放 0。"
                    "开场图可放 0，吐槽图放在对应调侃句后，安慰图放在接住情绪那句后，"
                    "收尾图放最后一条后。如果同时要发文字气泡，先调用本工具，再调用 "
                    "emit_chat_beats。"
                ),
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
