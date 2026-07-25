import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.security import InMemoryRateLimiter, RateLimitExceeded, RateLimitRule


class RateLimitTests(unittest.TestCase):
    def test_rolling_window_limit_returns_retry_after(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(key="chat:user-a", requests=2, window_seconds=60)

        limiter.consume([rule], now=100.0)
        limiter.consume([rule], now=110.0)

        with self.assertRaises(RateLimitExceeded) as error:
            limiter.consume([rule], now=120.0)

        self.assertEqual(error.exception.retry_after_seconds, 40)
        limiter.consume([rule], now=161.0)

    def test_daily_limit_resets_on_next_utc_day(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(key="voice:user-a", daily_requests=1)

        limiter.consume([rule], now=10.0)
        with self.assertRaises(RateLimitExceeded):
            limiter.consume([rule], now=20.0)

        limiter.consume([rule], now=86410.0)

    def test_rules_are_recorded_atomically(self):
        limiter = InMemoryRateLimiter()
        global_rule = RateLimitRule(key="chat:global", daily_requests=1)
        user_a_rule = RateLimitRule(key="chat:user-a", requests=1, window_seconds=60)
        user_b_rule = RateLimitRule(key="chat:user-b", requests=1, window_seconds=60)

        limiter.consume([user_a_rule, global_rule], now=100.0)
        with self.assertRaises(RateLimitExceeded):
            limiter.consume([user_b_rule, global_rule], now=101.0)

        limiter.consume([user_b_rule], now=101.0)


if __name__ == "__main__":
    unittest.main()
