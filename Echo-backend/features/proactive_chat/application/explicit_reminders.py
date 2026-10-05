from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


_RELATIVE_MINUTES = re.compile(
    r"(?P<amount>[0-9一二两三四五六七八九十百]+)\s*分钟(?:后|之后)"
)
_REMINDER_INTENT = re.compile(r"提醒(?:我)?\s*(?P<intent>.+)$")
_EXPLICIT_REMINDER = re.compile(
    r"(?:提醒(?:我)?|叫我|喊我|设置(?:一个)?(?:提醒|闹钟|定时))"
)
_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass(frozen=True)
class ExplicitRelativeReminder:
    local_datetime: datetime
    timezone: str
    intent: str
    user_visible_label: str


def _parse_amount(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "百" in value:
        parts = value.split("百", 1)
        hundreds = _parse_amount(parts[0]) or 1
        remainder = _parse_amount(parts[1]) if parts[1] else 0
        return hundreds * 100 + remainder
    if "十" in value:
        parts = value.split("十", 1)
        tens = _parse_amount(parts[0]) if parts[0] else 1
        remainder = _parse_amount(parts[1]) if parts[1] else 0
        return tens * 10 + remainder
    if all(char in _DIGITS for char in value):
        result = 0
        for char in value:
            result = result * 10 + _DIGITS[char]
        return result
    return None


def parse_explicit_relative_reminder(
    message: str,
    *,
    now: datetime,
    timezone: str = "Asia/Shanghai",
) -> ExplicitRelativeReminder | None:
    clean = " ".join(message.split()).strip()
    if not clean or not _EXPLICIT_REMINDER.search(clean):
        return None
    relative = _RELATIVE_MINUTES.search(clean)
    if relative is None:
        return None
    amount = _parse_amount(relative.group("amount"))
    if amount is None or amount <= 0 or amount > 24 * 60 * 30:
        return None
    intent_match = _REMINDER_INTENT.search(clean)
    intent = intent_match.group("intent").strip(" ，,。.!！?？") if intent_match else clean
    if not intent:
        return None
    ZoneInfo(timezone)
    local_now = now.astimezone(ZoneInfo(timezone))
    local_datetime = local_now + timedelta(minutes=amount)
    return ExplicitRelativeReminder(
        local_datetime=local_datetime,
        timezone=timezone,
        intent=intent[:500],
        user_visible_label=intent[:100],
    )
