# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.chat_action_routing import (
    ChatActionMode,
    route_chat_action,
)
from features.agent.domain.entities import AgentTurnResult
from features.agent.public import run_chat_agent
from shared.config import settings


class ChatActionRoutingTests(unittest.TestCase):
    def test_explicit_request_requires_tool(self):
        for message in (
            "去刷B站",
            "帮我看看B站",
            "去b站刷刷",
            "刷会儿视频",
            "（微信）叶子 对你说：去刷B站",
            "你去刷吧",
            "再刷一下",
        ):
            with self.subTest(message=message):
                route = route_chat_action(message)
                self.assertEqual(route.mode, ChatActionMode.EXPLICIT)
                self.assertTrue(route.require_tool)
                self.assertIn("bili_browse", route.allowed_tool_names)
                self.assertIn("bili_share", route.allowed_tool_names)

    def test_suggest_request_does_not_require_tool(self):
        for message in ("好无聊", "没事干", "随便看看", "找点好玩的"):
            with self.subTest(message=message):
                route = route_chat_action(message)
                self.assertEqual(route.mode, ChatActionMode.SUGGEST)
                self.assertFalse(route.require_tool)
                self.assertTrue(route.instruction)

    def test_negation_wins(self):
        for message in ("别刷B站", "不想看视频", "不用去刷了"):
            with self.subTest(message=message):
                route = route_chat_action(message)
                self.assertEqual(route.mode, ChatActionMode.NONE)

    def test_plain_chat_is_not_routed(self):
        for message in ("今天天气怎么样", "在忙吗", "B站是不是很火"):
            with self.subTest(message=message):
                route = route_chat_action(message)
                self.assertEqual(route.mode, ChatActionMode.NONE)


class _FakeAgent:
    def __init__(self):
        self.kwargs = None

    async def execute(self, *args, **kwargs):
        self.kwargs = kwargs
        return AgentTurnResult(reply_text="ok")


class ChatActionRoutingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _availability(self):
        return SimpleNamespace(
            desktop_online=True,
            phone_online=False,
            echo_computer_online=True,
        )

    async def test_explicit_request_narrows_tools_and_requires_call(self):
        fake = _FakeAgent()
        with (
            patch("features.agent.public.get_chat_agent", return_value=fake),
            patch(
                "features.agent.public.load_tool_availability",
                new=AsyncMock(return_value=self._availability()),
            ),
            patch.object(settings, "chat_action_routing_enabled", True),
        ):
            await run_chat_agent("u1", "（微信）叶子 对你说：去刷B站", [])

        self.assertTrue(fake.kwargs["require_tool"])
        self.assertIn("bili_browse", fake.kwargs["allowed_tool_names"])
        self.assertIn("bili_share", fake.kwargs["allowed_tool_names"])
        self.assertNotIn("computer_click", fake.kwargs["allowed_tool_names"])

    async def test_plain_message_keeps_full_toolset(self):
        fake = _FakeAgent()
        with (
            patch("features.agent.public.get_chat_agent", return_value=fake),
            patch(
                "features.agent.public.load_tool_availability",
                new=AsyncMock(return_value=self._availability()),
            ),
            patch.object(settings, "chat_action_routing_enabled", True),
            patch.object(settings, "chat_action_intent_enabled", False),
        ):
            await run_chat_agent("u1", "在忙吗", [])

        self.assertFalse(fake.kwargs["require_tool"])
        self.assertIn("computer_click", fake.kwargs["allowed_tool_names"])

    async def test_negative_message_does_not_route(self):
        fake = _FakeAgent()
        with (
            patch("features.agent.public.get_chat_agent", return_value=fake),
            patch(
                "features.agent.public.load_tool_availability",
                new=AsyncMock(return_value=self._availability()),
            ),
            patch.object(settings, "chat_action_routing_enabled", True),
            patch.object(settings, "chat_action_intent_enabled", False),
        ):
            await run_chat_agent("u1", "别刷B站", [])

        self.assertFalse(fake.kwargs["require_tool"])


if __name__ == "__main__":
    unittest.main()
