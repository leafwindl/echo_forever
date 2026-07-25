import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RateLimitRule:
    key: str
    requests: int = 0
    window_seconds: int = 0
    daily_requests: int = 0


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("Too many requests")
        self.retry_after_seconds = max(1, retry_after_seconds)


class InMemoryRateLimiter:
    """Single-instance rolling-window and UTC-day request limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}
        self._daily_counts: dict[str, tuple[int, int]] = {}

    def consume(self, rules: Iterable[RateLimitRule], now: float | None = None) -> None:
        current_time = time.time() if now is None else now
        active_rules = [
            rule
            for rule in rules
            if (rule.requests > 0 and rule.window_seconds > 0) or rule.daily_requests > 0
        ]
        if not active_rules:
            return

        utc_day = int(current_time // 86400)
        with self._lock:
            for rule in active_rules:
                self._check_rule(rule, current_time, utc_day)
            for rule in active_rules:
                self._record_rule(rule, current_time, utc_day)
            self._cleanup_if_needed(current_time, utc_day)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
            self._daily_counts.clear()

    def _check_rule(self, rule: RateLimitRule, now: float, utc_day: int) -> None:
        if rule.requests > 0 and rule.window_seconds > 0:
            timestamps = self._windows.setdefault(rule.key, deque())
            cutoff = now - rule.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= rule.requests:
                retry_after = math.ceil(rule.window_seconds - (now - timestamps[0]))
                raise RateLimitExceeded(retry_after)

        if rule.daily_requests > 0:
            stored_day, count = self._daily_counts.get(rule.key, (utc_day, 0))
            if stored_day != utc_day:
                count = 0
            if count >= rule.daily_requests:
                retry_after = math.ceil(((utc_day + 1) * 86400) - now)
                raise RateLimitExceeded(retry_after)

    def _record_rule(self, rule: RateLimitRule, now: float, utc_day: int) -> None:
        if rule.requests > 0 and rule.window_seconds > 0:
            self._windows.setdefault(rule.key, deque()).append(now)
        if rule.daily_requests > 0:
            stored_day, count = self._daily_counts.get(rule.key, (utc_day, 0))
            if stored_day != utc_day:
                count = 0
            self._daily_counts[rule.key] = (utc_day, count + 1)

    def _cleanup_if_needed(self, now: float, utc_day: int) -> None:
        if len(self._windows) > 10000:
            stale_before = now - 86400
            self._windows = {
                key: timestamps
                for key, timestamps in self._windows.items()
                if timestamps and timestamps[-1] > stale_before
            }
        if len(self._daily_counts) > 10000:
            self._daily_counts = {
                key: value for key, value in self._daily_counts.items() if value[0] == utc_day
            }


request_limiter = InMemoryRateLimiter()
