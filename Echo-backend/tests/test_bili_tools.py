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
    conversation_id = "conv_1"
    conversation_mode = "chat"


def _result(payload: dict) -> RemoteCommandResult:
    return RemoteCommandResult(ok=True, output=json.dumps(payload))


class BiliBrowseTests(unittest.IsolatedAsyncioTestCase):
    async def test_browse_starts_async_job(self):
        with patch(
            "features.desktop.public.start_bili_scan",
            return_value={
                "job_id": "bili_scan_1",
                "status": "pending",
                "reused": False,
            },
        ) as start:
            result = await _browse(_Context(), BiliBrowseArguments(limit=6))

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(result.data["status"], "started")
        self.assertEqual(result.data["job_id"], "bili_scan_1")
        self.assertEqual(start.call_args.kwargs["item_limit"], 6)
        self.assertEqual(start.call_args.kwargs["conversation_id"], "conv_1")

    async def test_browse_reuses_running_job(self):
        with patch(
            "features.desktop.public.start_bili_scan",
            return_value={
                "job_id": "bili_scan_1",
                "status": "running",
                "reused": True,
            },
        ):
            result = await _browse(_Context(), BiliBrowseArguments())

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(result.data["status"], "already_running")

    async def test_browse_fails_when_job_cannot_start(self):
        with patch(
            "features.desktop.public.start_bili_scan",
            side_effect=RuntimeError("db down"),
        ):
            result = await _browse(_Context(), BiliBrowseArguments())

        self.assertEqual(result.status, AgentToolStatus.FAILED)
        self.assertEqual(result.error_code, "start_failed")

    async def test_browse_reports_chain_limit(self):
        with patch(
            "features.desktop.public.start_bili_scan",
            return_value={
                "blocked": True,
                "round": 3,
                "max_rounds": 3,
                "reused": False,
            },
        ):
            result = await _browse(_Context(), BiliBrowseArguments())

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(result.data["status"], "chain_limit")


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
