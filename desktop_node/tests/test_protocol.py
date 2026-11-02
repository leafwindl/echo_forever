from __future__ import annotations

import unittest

from echo_desktop.config import DesktopConfig
from echo_desktop.protocol import parse_command, result_payload


class ProtocolTests(unittest.TestCase):
    def test_parse_command_defaults_and_clamps_timeout(self):
        command = parse_command(
            {
                "command_id": "cmd-1",
                "action": "open_app",
                "arguments": {"app": "notepad"},
                "timeout_seconds": 500,
            }
        )
        self.assertEqual(command.command_id, "cmd-1")
        self.assertEqual(command.arguments["app"], "notepad")
        self.assertEqual(command.timeout_seconds, 120)

    def test_result_payload_shapes(self):
        success = result_payload("cmd-1", data={"pid": 1})
        self.assertTrue(success["ok"])
        self.assertEqual(success["data"]["pid"], 1)
        self.assertEqual(success["type"], "result")

    def test_websocket_url_uses_secure_scheme(self):
        config = DesktopConfig(
            server_url="https://api.echoaiforever.cn",
            node_id="dnode_1",
            node_name="PC",
            token="token",
        )
        self.assertEqual(
            config.websocket_url,
            "wss://api.echoaiforever.cn/desktop/nodes/ws",
        )
