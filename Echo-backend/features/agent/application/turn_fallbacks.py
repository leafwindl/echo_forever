"""一次 Agent turn 的确定性兜底文案。

不调用模型、不读写外部状态：只根据已经发生的工具结果，决定"这种情况下最低
限度该说什么"。单独成模块，是为了让兜底语料可读、可单独测，不和编排逻辑混在
一起。

注意：这些文案按业务语义区分工具名，是产品话术的一部分；运行时的通用分支
不应该依赖它们。
"""

from __future__ import annotations

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ContentPart,
)


class TurnFallbacks:
    def confirmation_for_completed_tool(self, results: list[AgentToolResult]) -> str:
        for result in reversed(results):
            if result.status != AgentToolStatus.COMPLETED:
                continue
            if result.tool_name == "create_chat_schedule" and result.data.get("created"):
                label = str(result.data.get("label") or "").strip()
                return (
                    f"好，已经帮你设置好了：{label}。"
                    if label
                    else "好，已经帮你设置好了。"
                )
            if result.tool_name == "cancel_chat_schedule" and result.data.get("cancelled"):
                return "好，这个提醒已经取消了。"
        return ""

    def call_tool_failure(self, results: list[AgentToolResult]) -> str:
        for result in reversed(results):
            if result.tool_name == "search_web":
                if result.status == AgentToolStatus.NO_RESULT:
                    return "这次没有查到可靠的结果，我们可以换个说法再试试。"
                if result.status == AgentToolStatus.FAILED:
                    return "这次联网查询没有完成，稍后再试试吧。"
            if (
                result.tool_name == "create_chat_schedule"
                and result.status != AgentToolStatus.COMPLETED
            ):
                return "这个提醒这次没有设置成功，我们再确认一下时间吧。"
            if (
                result.tool_name == "list_chat_schedules"
                and result.status == AgentToolStatus.FAILED
            ):
                return "我这次没能读取你的提醒，稍后再试试吧。"
            if (
                result.tool_name == "cancel_chat_schedule"
                and result.status != AgentToolStatus.COMPLETED
            ):
                return "我没有找到要取消的提醒，我们可以再确认一下。"
        return ""

    def no_sticker_reply(self, results: list[AgentToolResult]) -> str:
        sticker_results = [
            result for result in results if result.tool_name == "send_sticker"
        ]
        if any(result.status == AgentToolStatus.NO_RESULT for result in sticker_results):
            return "这次没找到合适的表情包，我先不乱发。"
        if sticker_results:
            return "这次表情包没有发出去，我们先继续聊。"
        return "我在，继续和你说。"

    def disaster(self, content_parts: list[ContentPart] | tuple[ContentPart, ...]) -> str:
        if any(part.type == "sticker" for part in content_parts):
            return "这张给你。"
        return "刚才这次回复没有完成，再和我说一次好吗？"
