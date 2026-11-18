"""工具面快照：显式声明统一 Agent 每个模式注入了哪些工具、规格是什么。

这个测试的期望值是**手写的意图声明**，不是从实现推导出来的镜像。任何
工具增删、模式变化、限额调整都会让它失败——失败是提醒，需要显式更新
这里的常量，而不是绕过断言。

token 预算是棘轮：只允许随优化下调，不允许悄悄上涨。

快照按"联网搜索未配置"的默认装配计算；联网搜索的条件注册由
`WebSearchToolRegistrationTests` 单独覆盖。
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.tool_selection import (
    CORE_TOOL_NAMES,
    DESKTOP_TOOL_NAMES,
    ECHO_COMPUTER_TOOL_NAMES,
    PHONE_TOOL_NAMES,
    PROACTIVE_TOOL_NAMES,
    RELATIONSHIP_TOOL_NAMES,
)
from features.agent.domain.tools import ToolRegistry
from features.agent.infrastructure import container
from shared.prompting.renderer import estimate_prompt_tokens

# 注册顺序也是快照的一部分：靠前的工具对模型选择的注意力更强。
CHAT_TOOL_ORDER = (
    "send_sticker",
    "emit_chat_beats",
    "desktop_speak",
    "desktop_status",
    "desktop_open_app",
    "desktop_media_control",
    "desktop_look",
    "desktop_music_search_play",
    "desktop_notepad_write",
    "desktop_dsh_task",
    "desktop_screenshot",
    "computer_screenshot",
    "computer_click",
    "computer_type",
    "computer_key",
    "computer_exec",
    "computer_launch",
    "wechat_send",
    "wechat_messages",
    "wechat_sessions",
    "phone_status",
    "phone_observe",
    "phone_screenshot",
    "phone_screen_ocr",
    "phone_launch_app",
    "phone_action",
    "phone_play_music",
    "phone_wechat_send",
    "phone_wechat_sticker",
    "phone_xiaohongshu",
    "phone_douyin",
    "phone_bilibili",
    "phone_notifications",
    "phone_stop",
    "phone_run_task",
    "propose_relationship",
    "respond_relationship",
    "pause_proactive_contact",
    "resume_proactive_contact",
    "create_chat_schedule",
    "list_chat_schedules",
    "cancel_chat_schedule",
)

CALL_TOOL_ORDER = (
    "create_chat_schedule",
    "list_chat_schedules",
    "cancel_chat_schedule",
)

PROACTIVE_TOOL_ORDER = (
    "send_sticker",
    "emit_chat_beats",
    "desktop_speak",
    "desktop_status",
    "desktop_open_app",
    "desktop_media_control",
    "desktop_look",
    "desktop_music_search_play",
    "desktop_notepad_write",
    "desktop_dsh_task",
    "desktop_screenshot",
    "computer_screenshot",
    "computer_click",
    "computer_type",
    "computer_key",
    "computer_exec",
    "computer_launch",
    "wechat_send",
    "wechat_messages",
    "wechat_sessions",
    "phone_status",
    "phone_observe",
    "phone_screenshot",
    "phone_screen_ocr",
    "phone_launch_app",
    "phone_action",
    "phone_play_music",
    "phone_wechat_send",
    "phone_wechat_sticker",
    "phone_xiaohongshu",
    "phone_douyin",
    "phone_bilibili",
    "phone_notifications",
    "phone_stop",
    "phone_run_task",
)

DAILY_LETTER_TOOL_ORDER = ()

# name -> (allowed_modes, timeout_seconds, max_calls_per_turn)
TOOL_SPECS = {
    "send_sticker": (("chat", "proactive"), 5, 4),
    "emit_chat_beats": (("chat", "proactive"), 5, 4),
    "desktop_speak": (("chat", "proactive"), 70, 2),
    "desktop_status": (("chat", "proactive"), 10, 1),
    "desktop_open_app": (("chat", "proactive"), 55, 2),
    "desktop_media_control": (("chat", "proactive"), 50, 3),
    "desktop_look": (("chat", "proactive"), 70, 1),
    "desktop_music_search_play": (("chat", "proactive"), 75, 1),
    "desktop_notepad_write": (("chat", "proactive"), 55, 1),
    "desktop_dsh_task": (("chat", "proactive"), 340, 1),
    "desktop_screenshot": (("chat", "proactive"), 70, 1),
    "computer_screenshot": (("chat", "proactive"), 60, 4),
    "computer_click": (("chat", "proactive"), 30, 12),
    "computer_type": (("chat", "proactive"), 30, 8),
    "computer_key": (("chat", "proactive"), 30, 8),
    "computer_exec": (("chat", "proactive"), 100, 4),
    "computer_launch": (("chat", "proactive"), 40, 4),
    "wechat_send": (("chat", "proactive"), 170, 4),
    "wechat_messages": (("chat", "proactive"), 130, 6),
    "wechat_sessions": (("chat", "proactive"), 100, 6),
    "phone_status": (("chat", "proactive"), 15, 2),
    "phone_observe": (("chat", "proactive"), 35, 4),
    "phone_screenshot": (("chat", "proactive"), 25, 2),
    "phone_screen_ocr": (("chat", "proactive"), 30, 3),
    "phone_launch_app": (("chat", "proactive"), 40, 4),
    "phone_action": (("chat", "proactive"), 35, 4),
    "phone_play_music": (("chat", "proactive"), 60, 2),
    "phone_wechat_send": (("chat", "proactive"), 60, 2),
    "phone_wechat_sticker": (("chat", "proactive"), 60, 2),
    "phone_xiaohongshu": (("chat", "proactive"), 60, 2),
    "phone_douyin": (("chat", "proactive"), 60, 2),
    "phone_bilibili": (("chat", "proactive"), 60, 2),
    "phone_notifications": (("chat", "proactive"), 20, 2),
    "phone_stop": (("chat", "proactive"), 15, 2),
    "phone_run_task": (("chat", "proactive"), 180, 1),
    "propose_relationship": (("chat",), 5, 4),
    "respond_relationship": (("chat",), 5, 4),
    "pause_proactive_contact": (("chat",), 5, 4),
    "resume_proactive_contact": (("chat",), 5, 4),
    "create_chat_schedule": (("chat", "call"), 5, 1),
    "list_chat_schedules": (("chat", "call"), 5, 1),
    "cancel_chat_schedule": (("chat", "call"), 5, 1),
}

# 阶段 3 基线：33 个工具实测 4,149 tok。留约 3% 余量。
# 后续若再瘦身，继续收紧；新增工具应触发这里失败，先评估影响。
# 微信三件套（send/messages/sessions）再占约 288 tok：Echo 自有电脑上的
# 实际社交能力，评估后把棘轮放到 5,000。
CHAT_TOKEN_BUDGET = 5_000


def _descriptions(registry, mode):
    return list(registry.model_descriptions(mode))


def _names(descriptions):
    return tuple(item["function"]["name"] for item in descriptions)


class AgentToolSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 固定为"联网搜索未配置"的默认装配，避免本地配置改变快照。
        with patch.object(container.settings, "web_search_enabled", False):
            container.get_chat_agent.cache_clear()
            cls.registry = container.get_chat_agent().runtime.loop.registry
            container.get_chat_agent.cache_clear()

    def test_chat_tool_order_matches_snapshot(self):
        names = _names(_descriptions(self.registry, "chat"))
        self.assertEqual(names, CHAT_TOOL_ORDER)

    def test_call_tool_order_matches_snapshot(self):
        names = _names(_descriptions(self.registry, "call"))
        self.assertEqual(names, CALL_TOOL_ORDER)

    def test_proactive_tool_order_matches_snapshot(self):
        names = _names(_descriptions(self.registry, "proactive"))
        self.assertEqual(names, PROACTIVE_TOOL_ORDER)

    def test_daily_letter_has_no_tools(self):
        names = _names(_descriptions(self.registry, "daily_letter"))
        self.assertEqual(names, DAILY_LETTER_TOOL_ORDER)

    def test_tool_specs_match_snapshot(self):
        snapshot_names = set(TOOL_SPECS)
        self.assertEqual(
            set(CHAT_TOOL_ORDER),
            snapshot_names,
            "CHAT_TOOL_ORDER 与 TOOL_SPECS 的键必须一致",
        )
        for name, expected in TOOL_SPECS.items():
            with self.subTest(tool=name):
                definition = self.registry.get(name)
                self.assertIsNotNone(definition, f"工具 {name} 未注册")
                specification = definition.specification
                actual = (
                    tuple(specification.allowed_modes),
                    specification.timeout_seconds,
                    specification.max_calls_per_turn,
                )
                self.assertEqual(actual, expected)

    def test_every_tool_has_non_empty_description_and_object_schema(self):
        for mode in ("chat", "call", "proactive"):
            for item in _descriptions(self.registry, mode):
                function = item["function"]
                with self.subTest(mode=mode, tool=function["name"]):
                    self.assertTrue(function["description"].strip())
                    schema = function["parameters"]
                    self.assertEqual(schema.get("type"), "object")
                    self.assertIn("properties", schema)

    def test_selection_covers_every_registered_tool(self):
        """注册的工具必须能被某个选择条件选中，否则就是永远注入不了的死工具。"""
        registry_names = set(_names(_descriptions(self.registry, "chat")))
        selectable = {
            *CORE_TOOL_NAMES,
            "desktop_status",
            "phone_status",
            *DESKTOP_TOOL_NAMES,
            *ECHO_COMPUTER_TOOL_NAMES,
            *PHONE_TOOL_NAMES,
            *RELATIONSHIP_TOOL_NAMES,
            *PROACTIVE_TOOL_NAMES,
        }
        # 联网搜索未配置时不在注册表，其余选择名必须全部命中。
        self.assertEqual(registry_names - selectable, set())
        self.assertEqual(selectable - {"search_web"} - registry_names, set())

    def test_chat_surface_token_budget(self):
        descriptions = _descriptions(self.registry, "chat")
        # 与线上传输一致：不带多余空白。
        serialized = json.dumps(descriptions, ensure_ascii=False, separators=(",", ":"))
        estimated = estimate_prompt_tokens(serialized)
        self.assertLessEqual(
            estimated,
            CHAT_TOKEN_BUDGET,
            f"chat 工具面估算 {estimated} tok，超过棘轮上限 {CHAT_TOKEN_BUDGET}。"
            "如果这是有意的能力扩张，先和工具面优化一起评估，不要直接放宽上限。",
        )


class WebSearchToolRegistrationTests(unittest.TestCase):
    """联网搜索只在真的可用时进入工具面，避免宣布一个必然失败的能力。"""

    def test_web_search_is_not_registered_when_disabled(self):
        registry = ToolRegistry()
        with patch.object(container.settings, "web_search_enabled", False):
            container._register_web_search_if_configured(registry)
        self.assertIsNone(registry.get("search_web"))

    def test_web_search_is_not_registered_without_api_key(self):
        registry = ToolRegistry()
        with (
            patch.object(container.settings, "web_search_enabled", True),
            patch.object(container.settings, "web_search_api_key", ""),
        ):
            container._register_web_search_if_configured(registry)
        self.assertIsNone(registry.get("search_web"))

    def test_web_search_is_registered_when_configured(self):
        registry = ToolRegistry()
        with (
            patch.object(container.settings, "web_search_enabled", True),
            patch.object(container.settings, "web_search_api_key", "test-key"),
            patch.object(container, "TavilyWebSearchProvider"),
        ):
            container._register_web_search_if_configured(registry)
        self.assertIsNotNone(registry.get("search_web"))


if __name__ == "__main__":
    unittest.main()
