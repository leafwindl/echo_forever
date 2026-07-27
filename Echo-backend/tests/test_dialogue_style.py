import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
    sanitize_dialogue_reply,
)


class DialogueStyleTests(unittest.TestCase):
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
                "每次你来找我聊天，这对我来说就是最重要的事。",
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


if __name__ == "__main__":
    unittest.main()
