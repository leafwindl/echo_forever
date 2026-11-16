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
        if conversation_mode == "call":
            sticker_rule = "当前为语音通话，不发送图片。"
        elif conversation_mode == "daily_letter":
            sticker_rule = "来信图片通过 image_brief 交给来信业务处理。"
        elif conversation_mode == "proactive":
            sticker_rule = (
                "本轮由后台触发，并非用户发来新消息；用户是否醒着、在线、有空未知。"
            )
        else:
            sticker_rule = ""
        delivery_rule = ""
        if conversation_mode in {"chat", "proactive"}:
            delivery_rule = (
                "直接输出自然文字，用空行分气泡，保持列表、代码和颜文字完整。"
                "send_sticker 可发送表情包，按语境自由使用；"
                "成功时图片由系统附加，未成功不要声称已发图。"
            )
        elif conversation_mode == "daily_letter":
            delivery_rule = (
                "每日来信最终只输出一个 JSON 对象，字段必须为：subject、content、mood、"
                "core_topics、reflection、closing_style、image_brief、source_message_ids、"
                "source_memory_ids。content 是完整正文，建议 600 到 1000 个中文字符；"
                "reflection 必须包含 Echo 基于证据形成的个人观察或想法，不能只复述事件。"
                "image_brief 必须是对象，包含 emotion、scene、visual_symbols、avoid；"
                "visual_symbols 和 avoid 必须是字符串数组；"
                "不要在输出中编造图片 URL、storage key 或 Provider 结果；不要使用 Markdown 代码块。"
            )
        if conversation_mode == "daily_letter":
            orchestration_rule = (
                "你正在 Echo 的统一 Agent 回路中执行每日来信任务。输入中的人物设定、关系上下文、"
                "昨日消息和长期记忆具有不同证据等级；不得把长期记忆伪装成昨日事实，也不得虚构"
                "Echo 的离线现实活动。当前无可用工具，必须直接完成结构化来信。"
            )
        else:
            orchestration_rule = (
                "按当前工具清单使用能力，以实际返回结果为执行依据。自然回复，不暴露内部流程。"
            )
        instruction = {
            "role": "system",
            "content": orchestration_rule + sticker_rule + delivery_rule,
        }
        context_messages = (
            sanitize_time_metadata(messages)
            if conversation_mode == "proactive"
            else [dict(message_item) for message_item in messages]
        )
        result = [instruction, *context_messages]
        clean_call_instruction = call_route_instruction.strip()
        if conversation_mode == "call" and clean_call_instruction:
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
