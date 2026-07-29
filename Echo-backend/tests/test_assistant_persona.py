import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.assistant_persona.public import (
    AssistantPersonaNotFoundError,
    get_assistant_persona,
)


class AssistantPersonaTests(unittest.TestCase):
    def test_echo_persona_v1_has_stable_behavior_contract(self):
        persona = get_assistant_persona("echo-persona-v1")

        self.assertEqual("Echo", persona.name)
        self.assertIn("不同世界", persona.role)
        self.assertIn("温柔但不溺爱", persona.traits[0])
        self.assertTrue(any("简短不等于冷淡" in item for item in persona.conversation_principles))
        self.assertTrue(any("温暖是初识" in item for item in persona.conversation_principles))
        self.assertTrue(any("共同进步" in item for item in persona.conversation_principles))
        self.assertTrue(any("人类生活史" in item for item in persona.forbidden_claims))

    def test_unknown_persona_version_is_rejected(self):
        with self.assertRaises(AssistantPersonaNotFoundError):
            get_assistant_persona("missing-persona")


if __name__ == "__main__":
    unittest.main()
