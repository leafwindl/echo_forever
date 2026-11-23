# ruff: noqa: ARG001, ARG002
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import AgentToolStatus
from features.agent.infrastructure.tools.bili_tools import (
    BiliBrowseArguments,
    BiliShareArguments,
    _browse,
    _share,
)
from features.desktop.public import RemoteCommandResult


class _Context:
    user_id = "phone_1"


def _result(payload: dict) -> RemoteCommandResult:
    return RemoteCommandResult(ok=True, output=json.dumps(payload))


class BiliBrowseTests(unittest.IsolatedAsyncioTestCase):
    async def test_browse_returns_titles_and_frames_without_base64(self):
        payload = {
            "ok": True,
            "items": [
                {
                    "ok": True,
                    "title": "视频A",
                    "frame": r"C:\EchoComputer\images\bili_scan_0.png",
                    "frame_base64": "A" * 100,
                },
                {
                    "ok": True,
                    "title": "视频B",
                    "frame": r"C:\EchoComputer\images\bili_scan_1.png",
                    "frame_base64": "B" * 100,
                },
            ],
        }
        with patch(
            "features.agent.infrastructure.tools.bili_tools.run_desktop_command",
            new=AsyncMock(return_value=_result(payload)),
        ):
            result = await _browse(_Context(), BiliBrowseArguments(limit=2))

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(
            [item["frame"] for item in result.data["items"]],
            ["bili_scan_0.png", "bili_scan_1.png"],
        )
        self.assertNotIn("AAAA", result.safe_for_model)

    async def test_browse_reports_empty_round(self):
        with patch(
            "features.agent.infrastructure.tools.bili_tools.run_desktop_command",
            new=AsyncMock(return_value=_result({"ok": True, "items": []})),
        ):
            result = await _browse(_Context(), BiliBrowseArguments())

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(result.data["items"], [])


class BiliShareTests(unittest.IsolatedAsyncioTestCase):
    async def test_share_sends_image_then_records_history(self):
        calls: list[str] = []

        async def fake_run(command: str, **kwargs):
            calls.append(command)
            if "/send_image" in command:
                return _result({"ok": True})
            if "/frame" in command:
                return _result({"ok": True, "image_base64": "QUJD"})
            return _result({"ok": True})

        history = AsyncMock()
        with (
            patch(
                "features.agent.infrastructure.tools.bili_tools.run_desktop_command",
                new=fake_run,
            ),
            patch(
                "features.agent.infrastructure.tools.bili_tools._store_frame",
                return_value="https://cos.example/f.png",
            ),
            patch(
                "features.chat.public.deliver_external_assistant_message",
                new=history,
            ),
        ):
            result = await _share(
                _Context(),
                BiliShareArguments(
                    frame="bili_scan_0.png",
                    title="视频A",
                    note="这画面好刺激",
                ),
            )

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertIn("/send_image", calls[0])
        history.assert_awaited_once()
        kwargs = history.await_args.kwargs
        self.assertEqual(kwargs["source"], "bili")
        self.assertIn("视频A", kwargs["content"])
        self.assertEqual(kwargs["content_parts"][0].url, "https://cos.example/f.png")

    async def test_share_fails_when_bridge_rejects(self):
        async def fake_run(command: str, **kwargs):
            return _result({"ok": False, "stderr": "file not found"})

        with patch(
            "features.agent.infrastructure.tools.bili_tools.run_desktop_command",
            new=fake_run,
        ):
            result = await _share(
                _Context(),
                BiliShareArguments(frame="bili_scan_0.png", note="x"),
            )

        self.assertEqual(result.status, AgentToolStatus.FAILED)
        self.assertEqual(result.error_code, "bridge_rejected")


if __name__ == "__main__":
    unittest.main()
