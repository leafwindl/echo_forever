"""好感度调整的纯规则：单次 ±10、每日净额 ±30、1–1000 上限。"""

MAX_SINGLE_DELTA = 10
DAILY_NET_LIMIT = 30
MIN_AFFECTION = 1
MAX_AFFECTION = 1000


def validate_adjustment(delta: int, reason: str) -> tuple[int, str]:
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise ValueError("affection delta must be an integer")
    if delta == 0:
        raise ValueError("affection delta must not be zero")
    if abs(delta) > MAX_SINGLE_DELTA:
        raise ValueError("affection delta must be between -10 and 10")
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("affection reason is required")
    if len(clean_reason) > 120:
        raise ValueError("affection reason must be at most 120 characters")
    return delta, clean_reason


def cap_daily_delta(delta: int, daily_net: int) -> int:
    """把单次 delta 压到当日剩余额度内；daily_net 是已发生的净变化。"""
    if delta > 0:
        return max(0, min(delta, DAILY_NET_LIMIT - daily_net))
    return min(0, max(delta, -DAILY_NET_LIMIT - daily_net))


def clamp_affection(value: int) -> int:
    return max(MIN_AFFECTION, min(MAX_AFFECTION, value))


def stage_for_affection(affection: int) -> str:
    if affection >= 800:
        return "beloved"
    if affection >= 500:
        return "lover"
    if affection >= 300:
        return "ambiguous"
    if affection >= 100:
        return "familiar"
    return "new"
