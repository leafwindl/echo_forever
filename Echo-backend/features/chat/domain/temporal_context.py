from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_DATE_OFFSETS = {"昨天": -1, "今天": 0, "明天": 1}
_DAY_PERIOD_ALIASES = {
    "早上": "上午",
    "上午": "上午",
    "下午": "下午",
    "晚上": "晚上",
}
_DATE_PERIOD_PATTERN = re.compile(r"(?:(昨天|今天|明天))?(早上|上午|下午|晚上)")
_RELATIVE_PATTERN = re.compile(r"刚刚|待会(?:儿)?|等会(?:儿)?|一会(?:儿)?")
_DATE_ONLY_PATTERN = re.compile(r"昨天|今天|明天")


def build_temporal_context(
    *,
    now_utc: datetime,
    timezone_name: str,
    user_message: str,
    conversation_timing: dict[str, object] | None,
) -> dict[str, object]:
    zone = _zone(timezone_name)
    local_now = _aware_utc(now_utc).astimezone(zone)
    context: dict[str, object] = {
        "local_datetime": local_now.isoformat(timespec="seconds"),
        "local_date": local_now.date().isoformat(),
        "local_time": local_now.strftime("%H:%M:%S"),
        "weekday": weekday_name(local_now),
        "day_period": day_period(local_now),
        "timezone": zone.key,
        "utc_offset": local_now.strftime("%z"),
        "resolved_expressions": resolve_temporal_expressions(user_message, local_now),
    }
    if conversation_timing:
        context["conversation_gap"] = _localize_conversation_timing(
            conversation_timing,
            zone,
        )
    return context


def resolve_temporal_expressions(text: str, local_now: datetime) -> list[dict[str, object]]:
    resolved: list[tuple[int, int, dict[str, object]]] = []

    def add(start_index: int, end_index: int, value: dict[str, object]) -> None:
        if any(start_index < end and end_index > start for start, end, _ in resolved):
            return
        resolved.append((start_index, end_index, value))

    for match in _DATE_PERIOD_PATTERN.finditer(text):
        date_text = match.group(1) or "今天"
        period_text = match.group(2)
        period = _DAY_PERIOD_ALIASES[period_text]
        target_date = local_now.date() + timedelta(days=_DATE_OFFSETS[date_text])
        start, end = _period_window(target_date, period, local_now.tzinfo)
        add(
            *match.span(),
            {
                "text": match.group(0),
                "kind": "day_period",
                "start": start.isoformat(timespec="seconds"),
                "end": end.isoformat(timespec="seconds"),
                "relation_to_now": _relation(local_now, start, end),
            },
        )

    for match in _RELATIVE_PATTERN.finditer(text):
        value = match.group(0)
        if value == "刚刚":
            start, end, relation = (
                local_now - timedelta(minutes=15),
                local_now,
                "recent_past",
            )
        else:
            start, end, relation = local_now, local_now + timedelta(hours=2), "near_future"
        add(
            *match.span(),
            {
                "text": value,
                "kind": "relative",
                "start": start.isoformat(timespec="seconds"),
                "end": end.isoformat(timespec="seconds"),
                "relation_to_now": relation,
                "precision": "approximate",
            },
        )

    for match in _DATE_ONLY_PATTERN.finditer(text):
        target_date = local_now.date() + timedelta(days=_DATE_OFFSETS[match.group(0)])
        start = datetime.combine(target_date, time.min, tzinfo=local_now.tzinfo)
        end = start + timedelta(days=1)
        add(
            *match.span(),
            {
                "text": match.group(0),
                "kind": "date",
                "start": start.isoformat(timespec="seconds"),
                "end": end.isoformat(timespec="seconds"),
                "relation_to_now": _relation(local_now, start, end),
            },
        )

    return [value for _, _, value in sorted(resolved, key=lambda item: item[0])]


def weekday_name(value: datetime) -> str:
    return _WEEKDAYS[value.weekday()]


def day_period(value: datetime) -> str:
    hour = value.hour
    if hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    if hour < 23:
        return "晚上"
    return "深夜"


def format_gap_seconds(seconds: int) -> str:
    clean = max(seconds, 0)
    hours, remainder = divmod(clean, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if not parts:
        parts.append(f"{remaining_seconds}秒")
    return "".join(parts)


def _period_window(
    target_date: date,
    period: str,
    timezone,
) -> tuple[datetime, datetime]:
    hours = {
        "上午": (6, 12),
        "下午": (12, 18),
        "晚上": (18, 24),
    }
    start_hour, end_hour = hours[period]
    start = datetime.combine(target_date, time(start_hour), tzinfo=timezone)
    if end_hour == 24:
        end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone)
    else:
        end = datetime.combine(target_date, time(end_hour), tzinfo=timezone)
    return start, end


def _relation(now: datetime, start: datetime, end: datetime) -> str:
    if now < start:
        return "future"
    if now >= end:
        return "past"
    return "current"


def _localize_conversation_timing(
    timing: dict[str, object],
    zone: ZoneInfo,
) -> dict[str, object]:
    result = {
        "gap_seconds": int(timing.get("gap_seconds") or 0),
        "state": str(timing.get("state") or "active"),
        "should_acknowledge_gap": bool(timing.get("should_acknowledge_gap")),
    }
    for source, target in (
        ("current_message_at", "current_message_at"),
        ("previous_user_at", "previous_user_at"),
    ):
        parsed = _parse_datetime(timing.get(source))
        if parsed is not None:
            result[target] = parsed.astimezone(zone).isoformat(timespec="seconds")
    return result


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _aware_utc(datetime.fromisoformat(value.strip()))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
