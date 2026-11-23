# ruff: noqa: ARG001, ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.chat_action_routing import ChatActionMode
from features.agent.infrastructure.chat_action_intent import classify_chat_action


class ChatActionIntentTests(unittest.IsolatedAsyncioTestCase):
    async def _classify(self, content: str):
        provider = SimpleNamespace(
            chat_completion_message=AsyncMock(
                return_value=SimpleNamespace(content=content)
            )
        )
        with patch(
            "providers.llm_provider.get_llm_provider",
            return_value=provider,
        ):
            return await classify_chat_action("你去刷吧")

    async def test_explicit(self):
        route = await self._classify('{"mode": "explicit", "reason": "祈使"}')
        self.assertEqual(route.mode, ChatActionMode.EXPLICIT)
        self.assertTrue(route.require_tool)

    async def test_suggest(self):
        route = await self._classify('{"mode": "suggest", "reason": "无聊"}')
        self.assertEqual(route.mode, ChatActionMode.SUGGEST)
        self.assertFalse(route.require_tool)

    async def test_share_action(self):
        route = await self._classify(
            '{"action": "share", "mode": "explicit", "reason": "要分享"}'
        )
        self.assertEqual(route.action_kind, "share")
        self.assertIn("bili_share", route.allowed_tool_names)
        self.assertNotIn("bili_browse", route.allowed_tool_names)

    async def test_none(self):
        route = await self._classify('{"mode": "none", "reason": "闲聊"}')
        self.assertEqual(route.mode, ChatActionMode.NONE)

    async def test_failure_falls_back_to_none(self):
        provider = SimpleNamespace(
            chat_completion_message=AsyncMock(side_effect=RuntimeError("boom"))
        )
        with patch(
            "providers.llm_provider.get_llm_provider",
            return_value=provider,
        ):
            route = await classify_chat_action("你去刷吧")
        self.assertEqual(route.mode, ChatActionMode.NONE)


if __name__ == "__main__":
    unittest.main()
