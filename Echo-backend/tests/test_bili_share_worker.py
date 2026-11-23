# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.presence.infrastructure.bili_share_worker import (
    FALLBACK_SHARE_TEXT,
    _clean_description,
    _compose_share_text,
    _send_share,
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


class BiliShareSendTests(unittest.IsolatedAsyncioTestCase):
    async def _send(self, item: dict, output: str = '{"ok": true}') -> list[str]:
        commands: list[str] = []

        async def fake_run_remote(command: str, *, timeout_seconds: int = 480):  # noqa: ARG001
            commands.append(command)
            return True, output

        with (
            patch(
                "features.presence.infrastructure.bili_share_worker._compose_share_text",
                new=AsyncMock(return_value="这画面好刺激"),
            ),
            patch(
                "features.presence.infrastructure.bili_share_worker._run_remote_command",
                new=fake_run_remote,
            ),
        ):
            await _send_share(item)
        return commands

    async def test_send_share_uses_frame_path_through_send_image(self):
        commands = await self._send(
            {
                "title": "火山温泉",
                "frame": r"C:\EchoComputer\images\bili_scan_0.png",
                "frame_base64": "A" * 5000,
            }
        )

        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertIn("/send_image", command)
        self.assertIn("bili_scan_0.png", command)
        self.assertIn("这画面好刺激", command)
        # 帧内容不能进命令行，否则会被 Windows 命令行上限截断
        self.assertNotIn("AAAA", command)

    async def test_send_share_falls_back_to_text_when_frame_missing(self):
        commands = await self._send({"title": "t", "frame": ""})

        self.assertEqual(len(commands), 1)
        self.assertIn("/send_sequence", commands[0])
        self.assertIn("这画面好刺激", commands[0])

    async def test_send_share_reports_bridge_rejection(self):
        with self.assertLogs(level="WARNING") as captured:
            await self._send(
                {"title": "t", "frame": r"C:\EchoComputer\images\x.png"},
                output='{"ok": false, "stderr": "file not found: x.png"}',
            )

        self.assertTrue(any("bridge rejected" in line for line in captured.output))

    async def test_send_share_reports_non_json_bridge_output(self):
        with self.assertLogs(level="WARNING") as captured:
            await self._send(
                {"title": "t", "frame": r"C:\EchoComputer\images\x.png"},
                output="powershell.exe : 字符串缺少终止符",
            )

        self.assertTrue(any("non-json" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
