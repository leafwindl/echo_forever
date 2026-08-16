from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CallToolMode(StrEnum):
    FAST_CHAT = "fast_chat"
    WEB_SEARCH = "web_search"
    SCHEDULE_CREATE = "schedule_create"
    SCHEDULE_MANAGE = "schedule_manage"


@dataclass(frozen=True)
class CallToolRoute:
    mode: CallToolMode
    allowed_tool_names: tuple[str, ...] = ()
    maximum_tool_calls: int = 0
    instruction: str = ""


_SCHEDULE_NOUN = r"(?:提醒|定时|闹钟|任务)"
_SCHEDULE_CANCEL = re.compile(
    rf"(?:(?:取消|删除|删掉|关掉|不要).{{0,12}}{_SCHEDULE_NOUN}|"
    rf"{_SCHEDULE_NOUN}.{{0,12}}(?:取消|删除|删掉|关掉|不用))",
    re.IGNORECASE,
)
_SCHEDULE_LIST = re.compile(
    rf"(?:(?:哪些|什么|有什么|查看|看看|列出|查一下).{{0,12}}{_SCHEDULE_NOUN}|"
    rf"{_SCHEDULE_NOUN}.{{0,12}}(?:哪些|什么|有什么|查看|看看|列出))",
    re.IGNORECASE,
)
_SCHEDULE_CREATE = re.compile(
    r"提醒(?:我)?|叫我|喊我|设(?:置)?(?:一个)?(?:提醒|闹钟|定时)|"
    r"到时候.{0,8}(?:提醒|问我|叫我)|记得.{0,8}(?:提醒|叫我)",
    re.IGNORECASE,
)
_WEB_SEARCH = re.compile(
    r"搜索|搜一下|搜搜|联网查|网上查|上网查|帮我查|查一下(?:今天|最近|最新|新闻|网上)|"
    r"核实一下|验证一下|新闻|热搜|最新(?:消息|进展|情况)|"
    r"网上有没有|有没有.{0,10}(?:报道|消息|新闻)|今天发生了什么",
    re.IGNORECASE,
)


def route_call_tools(
    message: str,
    *,
    web_search_available: bool,
    schedule_tools_available: bool,
) -> CallToolRoute:
    clean = " ".join(message.split())
    if _SCHEDULE_CANCEL.search(clean) or _SCHEDULE_LIST.search(clean):
        if schedule_tools_available:
            return CallToolRoute(
                mode=CallToolMode.SCHEDULE_MANAGE,
                allowed_tool_names=("list_chat_schedules",),
                maximum_tool_calls=2,
            )
        return CallToolRoute(
            mode=CallToolMode.SCHEDULE_MANAGE,
            instruction=(
                "用户正在通过语音管理提醒，但当前通话没有开放提醒工具。"
                "简短说明这次无法查询或取消，不得声称已经执行。"
            ),
        )
    if _SCHEDULE_CREATE.search(clean):
        if schedule_tools_available:
            return CallToolRoute(
                mode=CallToolMode.SCHEDULE_CREATE,
                allowed_tool_names=("create_chat_schedule",),
                maximum_tool_calls=1,
            )
        return CallToolRoute(
            mode=CallToolMode.SCHEDULE_CREATE,
            instruction=(
                "用户正在通过语音设置提醒，但当前通话没有开放提醒工具。"
                "简短说明这次无法创建，不得声称已经设置成功。"
            ),
        )
    if _WEB_SEARCH.search(clean):
        if web_search_available:
            return CallToolRoute(
                mode=CallToolMode.WEB_SEARCH,
                allowed_tool_names=("search_web",),
                maximum_tool_calls=1,
            )
        return CallToolRoute(
            mode=CallToolMode.WEB_SEARCH,
            instruction=(
                "用户要求查询实时或外部信息，但当前联网搜索不可用。"
                "直接、简短地说明暂时无法联网核实，不要用模型内部知识冒充搜索结果。"
            ),
        )
    return CallToolRoute(mode=CallToolMode.FAST_CHAT)
