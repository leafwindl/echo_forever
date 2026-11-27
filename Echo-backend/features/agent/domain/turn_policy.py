"""一次 Agent turn 的纯规则。

模式差异在这里落成协议字段：交付形态、是否允许空交付、失败是否静默、工具范围、
步数与重试预算。编排层只消费这些字段，不再写 `if conversation_mode == ...`。
"""

from __future__ import annotations

from dataclasses import dataclass

from features.agent.domain.delivery import sanitize_time_metadata
from features.agent.domain.entities import AgentToolResult, AgentToolStatus

_CALL_TERMINAL_TOOLS = frozenset(
    {"search_web", "create_chat_schedule", "cancel_chat_schedule"}
)


@dataclass(frozen=True)
class RetryBudget:
    llm_timeout: int = 1
    delivery_format: int = 1
    sticker_claim: int = 1
    chat_length: int = 1


@dataclass(frozen=True)
class TurnProfile:
    mode: str
    structured_output: bool
    delivery_mode: str
    allow_empty_delivery: bool
    silent_on_failure: bool
    max_steps: int
    max_tool_calls: int
    retries: RetryBudget


class TurnPolicy:
    def __init__(
        self,
        *,
        max_steps: int,
        max_tool_calls: int,
        proactive_max_tool_calls: int = 5,
        retries: RetryBudget | None = None,
    ):
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.proactive_max_tool_calls = proactive_max_tool_calls
        self.retries = retries or RetryBudget()

    def profile(
        self,
        *,
        conversation_mode: str,
        tool_call_limit: int | None = None,
    ) -> TurnProfile:
        maximum_tool_calls = (
            self.max_tool_calls
            if tool_call_limit is None
            else min(self.max_tool_calls, max(tool_call_limit, 0))
        )
        if conversation_mode == "daily_letter":
            return TurnProfile(
                mode=conversation_mode,
                structured_output=True,
                delivery_mode="daily_letter",
                allow_empty_delivery=False,
                silent_on_failure=False,
                max_steps=self.max_steps,
                max_tool_calls=maximum_tool_calls,
                retries=self.retries,
            )
        if conversation_mode == "call":
            return TurnProfile(
                mode=conversation_mode,
                structured_output=False,
                delivery_mode="call",
                allow_empty_delivery=False,
                silent_on_failure=False,
                max_steps=self.max_steps,
                max_tool_calls=maximum_tool_calls,
                retries=self.retries,
            )
        if conversation_mode == "proactive":
            proactive_limit = (
                self.proactive_max_tool_calls
                if tool_call_limit is None
                else min(self.proactive_max_tool_calls, max(tool_call_limit, 0))
            )
            return TurnProfile(
                mode=conversation_mode,
                structured_output=False,
                delivery_mode="natural",
                allow_empty_delivery=True,
                silent_on_failure=True,
                max_steps=self.max_steps,
                max_tool_calls=proactive_limit,
                retries=self.retries,
            )
        return TurnProfile(
            mode=conversation_mode,
            structured_output=False,
            delivery_mode="natural",
            allow_empty_delivery=False,
            silent_on_failure=False,
            max_steps=self.max_steps,
            max_tool_calls=maximum_tool_calls,
            retries=self.retries,
        )

    def initial_messages(
        self,
        *,
        messages: list[dict],
        conversation_mode: str,
        message: str = "",
        sticker_intent: str = "",
        call_route_instruction: str = "",
    ) -> list[dict]:
        del message  # 触发语只用于路由，不再影响提示词内容
        context_messages = (
            sanitize_time_metadata(messages)
            if conversation_mode == "proactive"
            else [dict(message_item) for message_item in messages]
        )
        result = [*context_messages]
        clean_call_instruction = call_route_instruction.strip()
        if conversation_mode in {"call", "chat"} and clean_call_instruction:
            result.insert(
                1,
                {
                    "role": "system",
                    "content": clean_call_instruction,
                },
            )
        clean_intent = sticker_intent.strip()
        if clean_intent:
            result.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "当前用户消息附带的表情包可信语义为：" + clean_intent + "。"
                        "请理解其含义并回复，但这不等于用户要求 Echo 再发送一张。"
                    ),
                },
            )
        return result

    @staticmethod
    def next_tool_scope(
        *,
        conversation_mode: str,
        tool_name: str,
        result: AgentToolResult,
    ) -> tuple[str, ...] | None:
        """返回 None 表示不变；返回元组表示新的工具范围（空元组=不再提供工具）。"""
        if conversation_mode != "call":
            return None
        if tool_name in _CALL_TERMINAL_TOOLS:
            return ()
        if tool_name == "list_chat_schedules":
            schedules = result.data.get("schedules")
            if (
                result.status == AgentToolStatus.COMPLETED
                and isinstance(schedules, list)
                and schedules
            ):
                return ("cancel_chat_schedule",)
            return ()
        return None
