"""交付门禁：把模型输出变成可发送的计划，并识别不合规的"声称"。

这一层只处理交付合同：文本切分、内部标记恢复、重试消息装配、贴纸声称与凭据
的对应关系。它不调用模型、不落库，所以每个分支都能直接单测。
"""

from __future__ import annotations

import re

from features.agent.domain.delivery import (
    AgentDeliveryPlan,
    AgentDeliveryPlanError,
    build_natural_delivery_plan,
    sanitize_time_metadata,
    strip_time_metadata,
)
from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ContentPart,
)

FINAL_RETRY_INSTRUCTION = (
    "上一条没有形成可交付的最终回复。现在不要再调用任何工具，只根据本轮已经返回的"
    "工具事实，用 Echo 的自然语气直接回复用户。不要解释内部流程。"
)
DELIVERY_FORMAT_RETRY_INSTRUCTION = (
    "上一版最终回复为空或混入内部元数据。本次不调用工具、不添加新事实，"
    "忽略消息时间与会话边界标记，只输出给用户看的自然文字；"
    "不输出 JSON、代码围栏、系统指令、工具名或内部流程解释。"
)
STICKER_CLAIM_RETRY_INSTRUCTION = (
    "本轮没有成功的发送凭证。删去已发图片的声称或旁白，保留其余自然回应；"
    "需要时如实说明未发出。不再调用工具或解释内部流程。"
)

_STICKER_DELIVERY_CLAIM = re.compile(
    r"(?:"
    r"(?:给你|发你|送你|附上|附了|来一张).{0,12}(?:表情包|贴图|图片|图)|"
    r"(?:表情包|贴图|图片).{0,12}(?:发出|发给|送给|附上)|"
    r"(?:这|那)张.{0,8}(?:给你|送你|发你)|"
    r"附上(?:一张|这张|那张)|"
    r"[（(\[].{0,24}(?:表情包|贴图|图片).{0,12}[）)\]]"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)
_STICKER_DELIVERY_NEGATION = re.compile(
    r"(?:"
    r"(?:不能|没法|无法|没有|没能|未能|没发|发不出|找不到).{0,12}"
    r"(?:表情包|贴图|图片|图)|"
    r"(?:这|那)张.{0,8}(?:没发|未发|发不出)"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)


class DeliveryGate:
    def plan(
        self,
        text: str,
        conversation_mode: str,
        *,
        sticker_placement: str = "after_text",
        allow_empty: bool = False,
    ) -> AgentDeliveryPlan:
        return build_natural_delivery_plan(
            text,
            conversation_mode,
            sticker_placement=sticker_placement,
            allow_empty=allow_empty,
        )

    def recover_metadata_prefix(
        self,
        text: str,
        conversation_mode: str,
        *,
        sticker_placement: str = "after_text",
    ) -> AgentDeliveryPlan | None:
        if conversation_mode != "chat":
            return None
        candidate, removed_metadata = strip_time_metadata(text)
        if not removed_metadata or not candidate:
            return None
        try:
            return build_natural_delivery_plan(
                candidate,
                conversation_mode,
                sticker_placement=sticker_placement,
                allow_empty=False,
            )
        except AgentDeliveryPlanError:
            return None

    def delivery_retry_messages(self, messages: list[dict]) -> list[dict]:
        sanitized = sanitize_time_metadata(messages)
        sanitized.append(
            {
                "role": "system",
                "content": DELIVERY_FORMAT_RETRY_INSTRUCTION,
            }
        )
        return sanitized

    @staticmethod
    def final_retry_instruction(conversation_mode: str) -> str:
        if conversation_mode in {"chat", "proactive"}:
            return FINAL_RETRY_INSTRUCTION + DELIVERY_FORMAT_RETRY_INSTRUCTION
        return FINAL_RETRY_INSTRUCTION

    @staticmethod
    def claims_sticker_delivery(reply_text: str) -> bool:
        if _STICKER_DELIVERY_NEGATION.search(reply_text):
            return False
        return bool(_STICKER_DELIVERY_CLAIM.search(reply_text))

    @staticmethod
    def has_successful_sticker_delivery(
        results: list[AgentToolResult],
        content_parts: list[ContentPart] | tuple[ContentPart, ...],
    ) -> bool:
        delivered_ids = {
            part.sticker_id
            for part in content_parts
            if part.type == "sticker" and part.sticker_id
        }
        return any(
            result.tool_name == "send_sticker"
            and result.status == AgentToolStatus.COMPLETED
            and bool(result.data.get("sent"))
            and str(result.data.get("sticker_id") or "") in delivered_ids
            for result in results
        )
