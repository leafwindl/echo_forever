# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.presence.infrastructure.bili_share_worker import (
    FALLBACK_SHARE_TEXT,
    _clean_description,
    _compose_share_text,
)


class _Response:
    def __init__(self, content: str):
        self.content = content


class _Provider:
    def __init__(self, content: str = "", error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls: list[dict] = []

    async def chat_completion_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _Response(self.content)


class BiliShareComposeTests(unittest.IsolatedAsyncioTestCase):
    async def test_compose_returns_provider_text_without_writing_chat_history(self):
        provider = _Provider("这个画面冲击感好强")
        with (
            patch("providers.llm_provider.get_llm_provider", return_value=provider),
            patch(
                "features.chat.public.generate_chat_reply",
                side_effect=AssertionError("分享话术不能写聊天历史"),
            ),
        ):
            text = await _compose_share_text(
                {"title": "地表最强", "judge": "画面很有梗\n8"}
            )

        self.assertEqual(text, "这个画面冲击感好强")
        self.assertEqual(len(provider.calls), 1)
        prompt = provider.calls[0]["messages"][1]["content"]
        self.assertIn("地表最强", prompt)
        self.assertNotIn("\n8", prompt)

    async def test_compose_falls_back_when_provider_raises(self):
        provider = _Provider(error=RuntimeError("boom"))
        with patch("providers.llm_provider.get_llm_provider", return_value=provider):
            text = await _compose_share_text({"title": "标题", "judge": "画面描述"})

        self.assertEqual(text, FALLBACK_SHARE_TEXT)

    async def test_compose_falls_back_when_provider_returns_blank(self):
        provider = _Provider("   ")
        with patch("providers.llm_provider.get_llm_provider", return_value=provider):
            text = await _compose_share_text({"title": "标题", "judge": "画面描述"})

        self.assertEqual(text, FALLBACK_SHARE_TEXT)

    def test_clean_description_drops_score_line(self):
        self.assertEqual(_clean_description("画面有冲击力\n8"), "画面有冲击力")
        self.assertEqual(_clean_description("荒诞感很强\n\n7。"), "荒诞感很强")


if __name__ == "__main__":
    unittest.main()
