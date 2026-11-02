from __future__ import annotations

import unittest
from unittest.mock import patch

from echo_desktop.executor import execute_command
from echo_desktop.protocol import ActionError, Command


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_denied_command_does_not_launch(self):
        command = Command(command_id="c1", action="open_app", arguments={"app": "notepad"})

        async def deny(*_args, **_kwargs):
            return False

        with (
            patch("echo_desktop.executor.launch_app") as launch,
            self.assertRaises(ActionError) as caught,
        ):
            await execute_command(command, approval=deny)
        self.assertEqual(caught.exception.code, "user_denied")
        launch.assert_not_called()

    async def test_approved_open_app_dispatches(self):
        command = Command(command_id="c1", action="open_app", arguments={"app": "notepad"})

        async def allow(*_args, **_kwargs):
            return True

        with patch(
            "echo_desktop.executor.launch_app",
            return_value={"app": "notepad", "pid": 1},
        ) as launch:
            data = await execute_command(command, approval=allow)
        self.assertEqual(data["pid"], 1)
        launch.assert_called_once_with("notepad")

    async def test_unsupported_action_is_rejected_before_approval(self):
        command = Command(command_id="c1", action="shell", arguments={})
        called = False

        async def allow(*_args, **_kwargs):
            nonlocal called
            called = True
            return True

        with self.assertRaises(ActionError) as caught:
            await execute_command(command, approval=allow)
        self.assertEqual(caught.exception.code, "unsupported_action")
        self.assertFalse(called)
