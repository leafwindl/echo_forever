"""工具选择是纯函数：输入运行时事实，输出本轮要告诉模型的工具名。

这些用例不碰数据库，锁定的是"什么情况下会宣布哪些能力"。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.tool_selection import (
    CORE_TOOL_NAMES,
    DESKTOP_TOOL_NAMES,
    PHONE_TOOL_NAMES,
    PROACTIVE_CORE_TOOL_NAMES,
    PROACTIVE_DESKTOP_TOOL_NAMES,
    PROACTIVE_PHONE_TOOL_NAMES,
    PROACTIVE_TOOL_NAMES,
    RELATIONSHIP_TOOL_NAMES,
    ToolSelectionContext,
    select_chat_tool_names,
    select_proactive_tool_names,
)

OFFLINE_NAMES = {
    *CORE_TOOL_NAMES,
    "desktop_status",
    "phone_status",
    *RELATIONSHIP_TOOL_NAMES,
}


class ToolSelectionTests(unittest.TestCase):
    def test_offline_devices_keep_core_status_and_relationship(self):
        names = select_chat_tool_names(ToolSelectionContext(conversation_mode="chat"))

        self.assertIsNotNone(names)
        self.assertEqual(set(names), OFFLINE_NAMES)
        self.assertEqual(len(names), len(OFFLINE_NAMES))
        self.assertNotIn("desktop_open_app", names)
        self.assertNotIn("phone_action", names)

    def test_desktop_online_adds_desktop_pack_only(self):
        names = select_chat_tool_names(
            ToolSelectionContext(conversation_mode="chat", desktop_online=True)
        )

        self.assertEqual(set(names), OFFLINE_NAMES | set(DESKTOP_TOOL_NAMES))
        self.assertNotIn("phone_action", names)

    def test_phone_online_adds_phone_pack_only(self):
        names = select_chat_tool_names(
            ToolSelectionContext(conversation_mode="chat", phone_online=True)
        )

        self.assertEqual(set(names), OFFLINE_NAMES | set(PHONE_TOOL_NAMES))
        self.assertNotIn("desktop_open_app", names)

    def test_both_online_includes_device_operations_but_not_proactive(self):
        names = select_chat_tool_names(
            ToolSelectionContext(
                conversation_mode="chat",
                desktop_online=True,
                phone_online=True,
            )
        )

        self.assertEqual(
            set(names),
            OFFLINE_NAMES | set(DESKTOP_TOOL_NAMES) | set(PHONE_TOOL_NAMES),
        )
        self.assertFalse(set(names) & set(PROACTIVE_TOOL_NAMES))

    def test_proactive_keywords_add_contact_switch_tools(self):
        for message in ("以后别主动找我了", "暂停联系一段时间", "我想恢复联系"):
            with self.subTest(message=message):
                names = select_chat_tool_names(
                    ToolSelectionContext(conversation_mode="chat", trigger_message=message)
                )
                self.assertTrue(set(PROACTIVE_TOOL_NAMES).issubset(names))

    def test_ordinary_message_does_not_add_proactive_tools(self):
        names = select_chat_tool_names(
            ToolSelectionContext(conversation_mode="chat", trigger_message="今天好累啊")
        )

        self.assertFalse(set(names) & set(PROACTIVE_TOOL_NAMES))

    def test_non_chat_modes_keep_existing_behavior(self):
        for mode in ("call", "proactive", "daily_letter"):
            with self.subTest(mode=mode):
                self.assertIsNone(
                    select_chat_tool_names(ToolSelectionContext(conversation_mode=mode))
                )

    def test_selection_has_no_duplicates(self):
        names = select_chat_tool_names(
            ToolSelectionContext(
                conversation_mode="chat",
                trigger_message="别主动找我了",
                desktop_online=True,
                phone_online=True,
            )
        )

        self.assertEqual(len(names), len(set(names)))


class ProactiveToolSelectionTests(unittest.TestCase):
    def test_offline_keeps_only_autonomous_core(self):
        names = select_proactive_tool_names(
            ToolSelectionContext(conversation_mode="proactive")
        )

        self.assertEqual(set(names), set(PROACTIVE_CORE_TOOL_NAMES))

    def test_desktop_online_excludes_dsh_task(self):
        names = select_proactive_tool_names(
            ToolSelectionContext(conversation_mode="proactive", desktop_online=True)
        )

        self.assertEqual(
            set(names), set(PROACTIVE_CORE_TOOL_NAMES) | set(PROACTIVE_DESKTOP_TOOL_NAMES)
        )
        self.assertIn("desktop_music_search_play", names)
        self.assertNotIn("desktop_dsh_task", names)

    def test_phone_online_excludes_external_send_and_multi_step(self):
        names = select_proactive_tool_names(
            ToolSelectionContext(conversation_mode="proactive", phone_online=True)
        )

        self.assertEqual(
            set(names), set(PROACTIVE_CORE_TOOL_NAMES) | set(PROACTIVE_PHONE_TOOL_NAMES)
        )
        self.assertIn("phone_play_music", names)
        self.assertIn("phone_screenshot", names)
        self.assertNotIn("phone_wechat_send", names)
        self.assertNotIn("phone_wechat_sticker", names)
        self.assertNotIn("phone_run_task", names)

    def test_proactive_never_includes_relationship_or_schedule_tools(self):
        names = set(
            select_proactive_tool_names(
                ToolSelectionContext(
                    conversation_mode="proactive",
                    desktop_online=True,
                    phone_online=True,
                )
            )
        )

        for forbidden in (
            "adjust_affection",
            "request_stage_advance",
            "respond_stage_advance",
            "create_chat_schedule",
            "list_chat_schedules",
            "cancel_chat_schedule",
            "pause_proactive_contact",
            "resume_proactive_contact",
        ):
            self.assertNotIn(forbidden, names)

    def test_no_duplicates(self):
        names = select_proactive_tool_names(
            ToolSelectionContext(
                conversation_mode="proactive",
                desktop_online=True,
                phone_online=True,
            )
        )
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
