from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from features.agent.domain.entities import AgentToolStatus
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.infrastructure.tools.mobile_tools import (
    PhoneStatusArguments,
    register_mobile_agent_tools,
)


class MobileAgentToolTests(unittest.TestCase):
    def test_phone_status_lists_paired_devices(self):
        registry = ToolRegistry()
        register_mobile_agent_tools(registry)
        fake_devices = [
            SimpleNamespace(
                device=SimpleNamespace(
                    device_id="mdev_test",
                    name="测试手机",
                ),
                online=True,
            )
        ]
        with patch(
            "features.agent.infrastructure.tools.mobile_tools"
            ".list_mobile_agent_devices",
            return_value=fake_devices,
        ):
            definition = registry.get("phone_status")
            self.assertIsNotNone(definition)
            result = asyncio.run(
                definition.handler(
                    ToolExecutionContext(user_id="user-1"),
                    PhoneStatusArguments(),
                )
            )
        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertIn("测试手机", result.safe_for_model)
        self.assertIn("在线", result.safe_for_model)

    def test_mobile_tools_are_registered(self):
        registry = ToolRegistry()
        register_mobile_agent_tools(registry)
        for name in (
            "phone_status",
            "phone_observe",
            "phone_screen_ocr",
            "phone_screenshot",
            "phone_launch_app",
            "phone_action",
            "phone_play_music",
            "phone_bilibili",
            "phone_douyin",
            "phone_xiaohongshu",
            "phone_wechat_send",
            "phone_notifications",
            "phone_stop",
            "phone_run_task",
        ):
            self.assertIsNotNone(registry.get(name), name)


if __name__ == "__main__":
    unittest.main()
