"""聊天轮的行动路由：判断这句话是「明确让你去刷」还是「给你留了个行动的余地」。

和 call_routing 一样只做纯规则，不做模型调用。命中后由 run_chat_agent 收窄
工具面，并把 require_tool 一路传到模型层（tool_choice=required）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ChatActionMode(StrEnum):
    NONE = "none"
    EXPLICIT = "explicit"
    SUGGEST = "suggest"


@dataclass(frozen=True)
class ChatActionRoute:
    mode: ChatActionMode = ChatActionMode.NONE
    allowed_tool_names: tuple[str, ...] = ()
    instruction: str = ""
    require_tool: bool = False


# 明确否定优先，命中后一律不路由。
_NEGATION = re.compile(
    r"别刷|不要刷|不想刷|别看B站|不要看B站|不看B站|别去看|不用去刷|"
    r"别去B站|不想看视频|别放视频|不想看视频",
    re.IGNORECASE,
)

# 明确让你去做。
_EXPLICIT = re.compile(
    r"(?:去|帮我|给我|来|自己)?(?:去)?(?:刷|看看|逛|看)(?:一下|一会儿|会儿|下)?"
    r"(?:B站|b站|bilibili|视频)|"
    r"(?:去|上)(?:B站|b站)(?:看看|刷刷|刷会儿)?|"
    r"(?:去|帮我|给我)(?:刷|看)(?:点|些|个)?(?:视频|B站)",
    re.IGNORECASE,
)

# 省略宾语的短祈使：上文在聊B站时，用户常说“你去刷吧”“再刷一下”。
_SHORT_IMPERATIVE = re.compile(
    r"(?:你|那)?(?:去|再)刷(?:一下|一会儿|会儿|吧|吧啊)?\s*[。！!~～]?$",
    re.IGNORECASE,
)

# 半明确：没有直接命令，但给了行动的余地。
_SUGGEST = re.compile(
    r"无聊|没事干|没事做|随便看看|随便刷刷|找点好玩的|有什么好玩的|"
    r"想看点|想刷刷|想看视频|想刷视频|要不去看看|要不刷刷",
    re.IGNORECASE,
)

# 行动模式下保留的交付工具，避免只剩 B站 工具不会说话。
_BILI_TOOL_NAMES = ("bili_browse", "bili_share")
_DELIVERY_TOOL_NAMES = ("emit_chat_beats", "send_sticker")


def explicit_route() -> ChatActionRoute:
    return ChatActionRoute(
        mode=ChatActionMode.EXPLICIT,
        allowed_tool_names=(*_BILI_TOOL_NAMES, *_DELIVERY_TOOL_NAMES),
        instruction=(
            "用户明确让你去刷B站。先调用 bili_browse 看推荐流，再从结果里挑值得的"
            "用 bili_share 发给用户；不要只口头答应，也不要说自己已经去过。"
        ),
        require_tool=True,
    )


def suggest_route() -> ChatActionRoute:
    return ChatActionRoute(
        mode=ChatActionMode.SUGGEST,
        allowed_tool_names=(*_BILI_TOOL_NAMES, *_DELIVERY_TOOL_NAMES),
        instruction=(
            "用户没有直接下命令，只是给了你行动的余地。你可以直接调用 bili_browse"
            "去看看，也可以先提议一起看；不要假装已经去过，也不要为了用工具而硬做。"
        ),
        require_tool=False,
    )


def route_chat_action(message: str) -> ChatActionRoute:
    """返回聊天轮的行动路由；没有命中就返回 NONE。"""
    clean = " ".join(message.split())
    if not clean or _NEGATION.search(clean):
        return ChatActionRoute()
    if _EXPLICIT.search(clean) or _SHORT_IMPERATIVE.search(clean):
        return explicit_route()
    if _SUGGEST.search(clean):
        return suggest_route()
    return ChatActionRoute()


__all__ = [
    "ChatActionMode",
    "ChatActionRoute",
    "explicit_route",
    "route_chat_action",
    "suggest_route",
]
