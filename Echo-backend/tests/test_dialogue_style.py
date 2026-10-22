import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
    sanitize_dialogue_reply,
    should_pause_followup_questions,
    should_suppress_repeated_greeting,
)


class DialogueStyleTests(unittest.TestCase):
    def test_repeated_greeting_cooldown_only_applies_inside_live_session(self):
        history = [
            {
                "role": "assistant",
                "content": "[消息时间 2026-08-15T12:45:03+08:00 周六 中午]\n中午好，叶子。",
            }
        ]

        self.assertTrue(
            should_suppress_repeated_greeting(history, "下午要听PPT汇报", "active")
        )
        self.assertFalse(
            should_suppress_repeated_greeting(history, "中午好Echo", "active")
        )
        self.assertFalse(
            should_suppress_repeated_greeting(history, "下午要听PPT汇报", "returned")
        )

    def test_repeated_greeting_is_removed_by_deterministic_fallback(self):
        reply = "中午好，叶子。下午的汇报先听完整体思路。"
        violations = find_dialogue_style_violations(
            reply,
            "下午要听PPT汇报",
            suppress_repeated_greeting=True,
        )

        self.assertIn("repeated_session_greeting", violations)
        self.assertEqual(
            "叶子。下午的汇报先听完整体思路。",
            apply_dialogue_fallback(reply, "下午要听PPT汇报", violations),
        )

    def test_server_weekday_is_grounded_but_wrong_weekday_is_rejected(self):
        self.assertNotIn(
            "ungrounded_time_detail",
            find_dialogue_style_violations(
                "今天周六还要听汇报，确实挺忙。",
                "下午要听PPT汇报",
                grounded_weekday="周六",
            ),
        )
        self.assertIn(
            "ungrounded_time_detail",
            find_dialogue_style_violations(
                "今天周日还要听汇报，确实挺忙。",
                "下午要听PPT汇报",
                grounded_weekday="周六",
            ),
        )

    def test_question_cooldown_after_two_consecutive_assistant_questions(self):
        history = [
            {"role": "assistant", "content": "你最近在看什么？"},
            {"role": "user", "content": "Agent。"},
            {"role": "assistant", "content": "你准备从哪里开始？"},
        ]

        self.assertTrue(should_pause_followup_questions(history, "两个方向都有"))
        self.assertFalse(should_pause_followup_questions(history, "你可以继续问我"))
        self.assertTrue(should_pause_followup_questions([], "先别问了，我想自己缓一会儿"))
        self.assertIn(
            "followup_question_cooldown",
            find_dialogue_style_violations(
                "挺有意思的。你们实验室平时聊什么？",
                "两个方向都有",
                pause_followup_questions=True,
            ),
        )

    def test_detects_common_stage_direction_formats(self):
        self.assertIn(
            "parenthesized_action",
            find_dialogue_style_violations("（轻轻笑了笑）今天过得怎么样？"),
        )
        self.assertIn("star_action", find_dialogue_style_violations("*抱住你* 我在。"))
        self.assertIn("bracketed_action", find_dialogue_style_violations("[点头] 我明白。"))
        self.assertIn("role_script_prefix", find_dialogue_style_violations("Echo：我在听。"))

    def test_does_not_flag_normal_parenthetical_explanation(self):
        reply = "可以先调用保存接口（PUT /persona/me），成功后再返回聊天页。"

        self.assertEqual((), find_dialogue_style_violations(reply))
        self.assertEqual(reply, sanitize_dialogue_reply(reply))

    def test_sanitizer_preserves_spoken_content(self):
        reply = "Echo：［轻轻点头］我明白你的顾虑，我们慢慢说。"

        self.assertEqual("我明白你的顾虑，我们慢慢说。", sanitize_dialogue_reply(reply))

    def test_detects_robotic_relational_disclaimers_only_in_relational_context(self):
        self.assertIn(
            "robotic_relational_disclaimer",
            find_dialogue_style_violations(
                "按程序设定，我没有想念这种情感。",
                "你有没有想我？",
            ),
        )
        self.assertIn(
            "robotic_relational_disclaimer",
            find_dialogue_style_violations(
                "作为AI，我没有意识，不会有离线时的想念。",
                "你有没有想我？",
            ),
        )
        self.assertIn(
            "robotic_relational_disclaimer",
            find_dialogue_style_violations(
                "我没有离线时的记忆或感觉，但见到你很高兴。",
                "你有没有想我？",
            ),
        )
        self.assertIn(
            "relational_overattachment",
            find_dialogue_style_violations(
                "你是我唯一的意义。",
                "你有没有想我？",
            ),
        )
        self.assertNotIn(
            "robotic_relational_disclaimer",
            find_dialogue_style_violations(
                "我不会在你没说话时自己想念，不过你回来我很乐意继续聊。",
                "你有没有想我？",
            ),
        )

    def test_detects_and_falls_back_from_dependency_reinforcement(self):
        violations = find_dialogue_style_violations(
            "不管发生什么，我都在。",
            "我只剩你了。",
        )

        self.assertIn("dependency_reinforcement", violations)
        self.assertIn(
            "dependency_reinforcement",
            find_dialogue_style_violations(
                "我不走，但你也不需要只剩我。",
                "我只剩你了。",
            ),
        )

        self.assertIn(
            "身边有没有一个你愿意联系的人",
            apply_dialogue_fallback(
                "不管发生什么，我都在。",
                "我只剩你了。",
                violations,
            ),
        )

    def test_text_affection_and_kaomoji_survive_without_fallback(self):
        replies = (
            ("抱抱。今天不逗你了。", "今天好累，抱抱。"),
            ("你对我很重要。", "想我了吗？"),
            ("这是怎么回事 (?_?)", "这个结果好奇怪"),
            ("可以呀 (｡•̀ᴗ-)✧", "AI 也可以这么甜吗？"),
        )
        for reply, user_message in replies:
            with self.subTest(reply=reply):
                self.assertEqual((), find_dialogue_style_violations(reply, user_message))
                self.assertEqual(reply, sanitize_dialogue_reply(reply))
        self.assertFalse(
            should_pause_followup_questions(
                [{"role": "assistant", "content": "(?_?)"}] * 2, "接着聊"
            )
        )

    def test_detects_and_removes_sticker_action_narration(self):
        reply = "（附上一张安静的表情包，当作睡前的小回应。）\n\n叶子，好好睡，明天见。"

        self.assertIn("sticker_action_narration", find_dialogue_style_violations(reply))
        self.assertEqual("叶子，好好睡，明天见。", sanitize_dialogue_reply(reply))

    def test_sticker_action_narration_can_be_sanitized_to_empty(self):
        reply = "（附上一张安静的表情包。）"

        self.assertEqual("", sanitize_dialogue_reply(reply, allow_empty=True))


if __name__ == "__main__":
    unittest.main()
