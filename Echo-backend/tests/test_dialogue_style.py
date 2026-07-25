import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.domain.dialogue_style import (
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


if __name__ == "__main__":
    unittest.main()
