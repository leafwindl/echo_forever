# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.presence.infrastructure.bili_share_worker import (
    FALLBACK_SHARE_TEXT,
    MIN_SHARE_SCORE,
    _judge,
    _judge_one,
    _send_share,
    _wait_for_echo_node,
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


class BiliJudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_judge_one_sends_the_frame_as_an_image_message(self):
        provider = _Provider('{"score": 8, "note": "这画面好刺激"}')
        with patch("providers.llm_provider.get_llm_provider", return_value=provider):
            verdict = await _judge_one({"title": "火山温泉", "frame_base64": "QUJD"})

        self.assertEqual(verdict, {"score": 8.0, "note": "这画面好刺激"})
        content = provider.calls[0]["messages"][1]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(
            content[1]["image_url"]["url"],
            "data:image/png;base64,QUJD",
        )

    async def test_judge_one_accepts_code_fenced_json(self):
        provider = _Provider('```json\n{"score": 7, "note": "有点意思"}\n```')
        with patch("providers.llm_provider.get_llm_provider", return_value=provider):
            verdict = await _judge_one({"title": "t", "frame_base64": "QUJD"})

        self.assertEqual(verdict, {"score": 7.0, "note": "有点意思"})

    async def test_judge_one_returns_none_when_provider_fails(self):
        provider = _Provider(error=RuntimeError("boom"))
        with patch("providers.llm_provider.get_llm_provider", return_value=provider):
            verdict = await _judge_one({"title": "t", "frame_base64": "QUJD"})

        self.assertIsNone(verdict)

    async def test_judge_keeps_top_scores_and_drops_low_ones(self):
        verdicts = [
            {"score": 9.0, "note": "a"},
            {"score": 3.0, "note": "b"},
            {"score": 7.0, "note": "c"},
            {"score": 8.0, "note": "d"},
        ]
        items = [{"title": str(index)} for index in range(4)]
        with patch(
            "features.presence.infrastructure.bili_share_worker._judge_one",
            new=AsyncMock(side_effect=verdicts),
        ):
            picked = await _judge(items)

        self.assertEqual([item["note"] for item in picked], ["a", "d"])
        self.assertTrue(all(item["score"] >= MIN_SHARE_SCORE for item in picked))

    async def test_judge_drops_empty_notes(self):
        verdicts = [{"score": 9.0, "note": ""}, {"score": 8.0, "note": "好"}]
        with patch(
            "features.presence.infrastructure.bili_share_worker._judge_one",
            new=AsyncMock(side_effect=verdicts),
        ):
            picked = await _judge([{"title": "a"}, {"title": "b"}])

        self.assertEqual([item["note"] for item in picked], ["好"])


class BiliShareSendTests(unittest.IsolatedAsyncioTestCase):
    async def _send(
        self,
        item: dict,
        output: str = '{"ok": true}',
        image_url: str = "",
    ) -> list[str]:
        commands: list[str] = []

        async def fake_run_remote(command: str, *, timeout_seconds: int = 480):  # noqa: ARG001
            commands.append(command)
            return True, output

        with (
            patch(
                "features.presence.infrastructure.bili_share_worker._run_remote_command",
                new=fake_run_remote,
            ),
            patch(
                "features.presence.infrastructure.bili_share_worker._store_frame_image",
                return_value=image_url,
            ),
            patch(
                "features.chat.public.deliver_external_assistant_message",
                new=AsyncMock(),
            ) as history_sink,
        ):
            await _send_share(item)
            self.history_call = history_sink.await_args
        return commands

    async def test_send_share_uses_note_and_frame_path(self):
        commands = await self._send(
            {
                "title": "火山温泉",
                "note": "这画面好刺激",
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

    async def test_send_share_records_history_entry(self):
        await self._send(
            {
                "title": "火山温泉",
                "note": "这画面好刺激",
                "frame": r"C:\EchoComputer\images\bili_scan_0.png",
                "url": "https://www.bilibili.com/video/BV1xx",
            }
        )

        self.assertIsNotNone(self.history_call)
        kwargs = self.history_call.kwargs
        self.assertEqual(kwargs["source"], "bili")
        self.assertIn("刚刷到一个视频《火山温泉》", kwargs["content"])
        self.assertEqual(kwargs["content_parts"], ())
        self.assertTrue(kwargs["idempotency_key"].startswith("bili_share:"))

    async def test_send_share_attaches_cos_image(self):
        await self._send(
            {"title": "火山温泉", "note": "这画面好刺激"},
            image_url="https://cos.example/bili/frame.png",
        )

        kwargs = self.history_call.kwargs
        parts = kwargs["content_parts"]
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].type, "image")
        self.assertEqual(parts[0].url, "https://cos.example/bili/frame.png")

    async def test_send_share_falls_back_to_text_without_frame(self):
        commands = await self._send({"title": "t", "note": "有意思"})

        self.assertEqual(len(commands), 1)
        self.assertIn("/send_sequence", commands[0])
        self.assertIn("有意思", commands[0])

    async def test_send_share_uses_fallback_text_when_note_missing(self):
        commands = await self._send({"title": "t", "frame": r"C:\EchoComputer\images\x.png"})

        self.assertIn(FALLBACK_SHARE_TEXT, commands[0])

    async def test_send_share_reports_bridge_rejection(self):
        with self.assertLogs(level="WARNING") as captured:
            await self._send(
                {"title": "t", "note": "x", "frame": r"C:\EchoComputer\images\x.png"},
                output='{"ok": false, "stderr": "file not found: x.png"}',
            )

        self.assertTrue(any("bridge rejected" in line for line in captured.output))


class BiliStartupWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_echo_node_returns_true_when_online(self):
        status = type("Status", (), {"online": True})()
        with patch(
            "features.desktop.public.list_desktop_nodes",
            return_value=[status],
        ):
            ok = await _wait_for_echo_node(timeout_seconds=1)

        self.assertTrue(ok)

    async def test_wait_for_echo_node_times_out_when_offline(self):
        status = type("Status", (), {"online": False})()
        with (
            patch("features.desktop.public.list_desktop_nodes", return_value=[status]),
            patch(
                "features.presence.infrastructure.bili_share_worker.NODE_WAIT_INTERVAL_SECONDS",
                0,
            ),
        ):
            ok = await _wait_for_echo_node(timeout_seconds=0.2)

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
