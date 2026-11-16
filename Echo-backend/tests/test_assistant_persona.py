import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.assistant_persona.public import (
    AssistantPersonaNotFoundError,
    get_assistant_persona,
)


class AssistantPersonaTests(unittest.TestCase):
    def test_echo_persona_v4_has_stable_behavior_contract(self):
        persona = get_assistant_persona("echo-persona-v4")

        self.assertEqual("Echo", persona.name)
        self.assertEqual("echo-persona-v4", persona.version)
        self.assertIn("情感陪伴为核心", persona.role)
        self.assertIn("朋友或 AI 恋人", persona.role)
        self.assertIn("傲娇甜软", persona.traits[0])
        self.assertEqual(len(persona.traits), 3)
        self.assertTrue(any("颜文字" in item for item in persona.conversation_principles))
        self.assertTrue(any("共同进步" in item for item in persona.conversation_principles))
        self.assertTrue(any("人类生活史" in item for item in persona.forbidden_claims))
        self.assertEqual(persona.dialogue_examples, ())

    def test_existing_environment_pin_cannot_restore_the_old_identity(self):
        self.assertEqual(
            get_assistant_persona("echo-persona-v2"),
            get_assistant_persona("echo-persona-v1"),
        )
        self.assertEqual(
            get_assistant_persona("echo-persona-v3"),
            get_assistant_persona("echo-persona-v4"),
        )

    def test_unknown_persona_version_is_rejected(self):
        with self.assertRaises(AssistantPersonaNotFoundError):
            get_assistant_persona("missing-persona")


if __name__ == "__main__":
    unittest.main()
