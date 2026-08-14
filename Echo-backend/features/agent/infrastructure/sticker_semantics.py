from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from features.agent.domain.services import (
    AgentConversationModel,
    StickerRequestDecision,
    StickerSemanticAnalysisError,
    StickerToolPolicy,
)

_T = TypeVar("_T", bound=BaseModel)


class StickerRequestArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: Literal["required", "optional"]
    intent: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def require_intent_for_explicit_request(self):
        if self.policy == "required" and not self.intent.strip():
            raise ValueError("Explicit sticker requests require a semantic intent")
        return self


class StickerDeliveryClaimArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims_delivery: bool


class ProviderStickerSemanticAnalyzer:
    _REQUEST_TOOL_NAME = "classify_sticker_request"
    _CLAIM_TOOL_NAME = "classify_sticker_delivery_claim"

    def __init__(self, model: AgentConversationModel, retry_limit: int = 1):
        self.model = model
        self.retry_limit = retry_limit

    async def assess_request(
        self,
        message: str,
        messages: list[dict],
    ) -> StickerRequestDecision:
        recent_context = [
            {
                "role": item.get("role", "user"),
                "content": str(item.get("content") or ""),
            }
            for item in messages[-8:]
            if item.get("role") in {"user", "assistant"}
        ]
        if (
            recent_context
            and recent_context[-1]["role"] == "user"
            and recent_context[-1]["content"].strip() == message.strip()
        ):
            recent_context.pop()
        parsed = await self._call_function(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "判断当前用户这一条消息是否明确要求 Echo 现在发送一张表情包、贴图或图片。"
                        "只有明确的发送、给我一张、来一张、让我看看等请求才是 required；用户自己"
                        "发送表情包、谈论表情包、表达情绪或普通聊天都是 optional。结合近期对话解决"
                        "指代，但不要把历史请求当成当前请求。required 时 intent 用简洁自然语言概括"
                        "用户想要的情绪或语境，供语义检索使用；不要照抄整句，也不要堆关键词。"
                    ),
                },
                *recent_context,
                {
                    "role": "user",
                    "content": f"只判断这条当前消息：{message}",
                },
            ],
            tool_name=self._REQUEST_TOOL_NAME,
            description="返回当前消息的表情包工具策略和语义检索意图",
            arguments_model=StickerRequestArguments,
        )
        return StickerRequestDecision(
            policy=StickerToolPolicy(parsed.policy),
            intent=parsed.intent.strip(),
        )

    async def claims_sticker_delivery(self, reply_text: str) -> bool:
        parsed = await self._call_function(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "判断助手最终可见文字是否声称或明确暗示：本轮已经、正在或随文字附带发送"
                        "了一张表情包、贴图或图片。像‘给你这张’、‘附上一张’和动作旁白都算。"
                        "仅仅讨论图片、表示以后可以发、表达想发但尚未发、或诚实说明没找到/没发出，"
                        "不算已发送。只通过指定函数返回判断。"
                    ),
                },
                {"role": "user", "content": reply_text},
            ],
            tool_name=self._CLAIM_TOOL_NAME,
            description="判断文字是否声称本轮已经交付表情包或图片",
            arguments_model=StickerDeliveryClaimArguments,
        )
        return parsed.claims_delivery

    async def _call_function(
        self,
        *,
        messages: list[dict],
        tool_name: str,
        description: str,
        arguments_model: type[_T],
    ) -> _T:
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": arguments_model.model_json_schema(),
            },
        }
        tool_choice = {
            "type": "function",
            "function": {"name": tool_name},
        }
        attempt_messages = list(messages)
        for attempt in range(self.retry_limit + 1):
            response = await self.model.complete(
                attempt_messages,
                (tool,),
                structured_output=False,
                tool_choice=tool_choice,
            )
            matching_calls = [
                call for call in response.tool_calls if call.tool_name == tool_name
            ]
            if len(matching_calls) == 1:
                try:
                    return arguments_model.model_validate(matching_calls[0].arguments)
                except ValidationError:
                    pass
            if attempt < self.retry_limit:
                attempt_messages.append(
                    {
                        "role": "system",
                        "content": (
                            f"上一次没有通过 {tool_name} 返回唯一且合法的函数参数。"
                            "现在必须只调用指定函数，并严格满足参数 schema。"
                        ),
                    }
                )
        raise StickerSemanticAnalysisError(
            f"Model did not return a valid {tool_name} function call"
        )
