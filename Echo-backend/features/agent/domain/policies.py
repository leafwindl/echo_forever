from __future__ import annotations

import re


CURRENT_TIME_PATTERNS = (
    "几点",
    "现在时间",
    "当前时间",
    "今天几号",
    "今天星期",
    "明天几号",
    "昨天几号",
)
SEARCH_PATTERNS = (
    "搜索",
    "查一下",
    "查一查",
    "上网查",
    "最新",
    "新闻",
    "价格",
    "天气",
    "政策",
    "现任",
    "官网",
)


def needs_time_tool(message: str) -> bool:
    compact = re.sub(r"\s+", "", message)
    return any(pattern in compact for pattern in CURRENT_TIME_PATTERNS)


def needs_web_search(message: str) -> bool:
    compact = re.sub(r"\s+", "", message)
    return any(pattern in compact for pattern in SEARCH_PATTERNS)


def relative_day_offset(message: str) -> int:
    if "明天" in message:
        return 1
    if "昨天" in message:
        return -1
    return 0

