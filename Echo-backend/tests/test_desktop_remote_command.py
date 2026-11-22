# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.desktop.application.remote_command import run_remote_command
from features.desktop.domain.entities import (
    DesktopCommandResult,
    DesktopOfflineError,
    DesktopTimeoutError,
)


class FakeDesktopService:
    """按顺序返回剧本里的 data；异常对象直接抛出。"""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[tuple[str, dict]] = []

    async def execute(
        self,
        *,
        user_id: str,
        action: str,
        arguments: dict,
        timeout_seconds: int | None = None,
        node_id: str | None = None,
        owner_type: str = "user",
    ) -> DesktopCommandResult:
        self.calls.append((action, dict(arguments)))
        if not self.script:
            raise AssertionError("script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return DesktopCommandResult(command_id="cmd_1", node_id="node_1", data=item)


async def _run(script: list, *, timeout_seconds=5, poll_interval_seconds=0):
    service = FakeDesktopService(script)
    result = await run_remote_command(
        service,
        user_id="user_1",
        command="echo hi",
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return service, result


class RemoteCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_sync_agent_returns_output_directly(self):
        service, result = await _run([{"output": "hello", "exit_code": 0}])

        self.assertTrue(result.ok)
        self.assertEqual(result.output, "hello")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.status, "sync")
        self.assertEqual(service.calls, [("exec", {"command": "echo hi"})])

    async def test_polls_until_done_status(self):
        service, result = await _run(
            [
                {"job_id": 7},
                {"status": "running"},
                {"status": "done", "output": "scan ok", "exit_code": 0},
            ]
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output, "scan ok")
        self.assertEqual(result.status, "done")
        self.assertEqual(result.job_id, 7)
        self.assertEqual(
            service.calls,
            [
                ("exec", {"command": "echo hi"}),
                ("job_result", {"job_id": 7}),
                ("job_result", {"job_id": 7}),
            ],
        )

    async def test_accepts_completed_status_for_compatibility(self):
        _, result = await _run([{"job_id": 7}, {"status": "completed", "output": "ok"}])

        self.assertTrue(result.ok)
        self.assertEqual(result.output, "ok")
        self.assertEqual(result.status, "completed")

    async def test_failed_status_returns_output_as_reason(self):
        _, result = await _run([{"job_id": 7}, {"status": "failed", "output": "boom"}])

        self.assertFalse(result.ok)
        self.assertEqual(result.output, "boom")
        self.assertEqual(result.status, "failed")

    async def test_missing_job_fails_fast_instead_of_waiting_for_timeout(self):
        service, result = await _run(
            [{"job_id": 7}, {"status": "missing"}],
            timeout_seconds=30,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "missing")
        self.assertEqual(len(service.calls), 2)

    async def test_unknown_status_eventually_times_out(self):
        _, result = await _run(
            [{"job_id": 7}] + [{"status": "queued"}] * 200,
            timeout_seconds=0.05,
            poll_interval_seconds=0.001,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "timeout")

    async def test_poll_timeout_is_retried(self):
        _, result = await _run(
            [
                {"job_id": 7},
                DesktopTimeoutError(),
                {"status": "done", "output": "ok"},
            ],
            timeout_seconds=30,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output, "ok")

    async def test_consecutive_poll_timeouts_abort(self):
        _, result = await _run(
            [{"job_id": 7}]
            + [DesktopTimeoutError(), DesktopTimeoutError(), DesktopTimeoutError()],
            timeout_seconds=30,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "poll_timeout")

    async def test_offline_during_poll_aborts_immediately(self):
        _, result = await _run([{"job_id": 7}, DesktopOfflineError()], timeout_seconds=30)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "desktop_offline")

    async def test_submit_offline_reports_desktop_error(self):
        _, result = await _run([DesktopOfflineError()], timeout_seconds=30)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "desktop_offline")
        self.assertTrue(result.output)

    async def test_submit_timeout_reports_desktop_error(self):
        _, result = await _run([DesktopTimeoutError()], timeout_seconds=30)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "desktop_timeout")


if __name__ == "__main__":
    unittest.main()
