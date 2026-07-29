import unittest
from datetime import datetime, timezone

from features.agent.domain.policies import needs_time_tool, needs_web_search, relative_day_offset
from features.agent.domain.services import resolve_local_time


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


class AgentFeatureTests(unittest.TestCase):
    def test_agent_tool_trigger_policy_is_bounded(self):
        self.assertTrue(needs_time_tool("现在几点？"))
        self.assertTrue(needs_web_search("帮我查一下最新消息"))
        self.assertFalse(needs_web_search("今天有点累"))
        self.assertEqual(relative_day_offset("明天几号"), 1)

    def test_time_tool_uses_iana_timezone(self):
        result = resolve_local_time(FakeClock(), "Asia/Shanghai")
        self.assertEqual(result["local_datetime"], "2026-07-29T16:00:00+08:00")
        self.assertEqual(result["timezone"], "Asia/Shanghai")
