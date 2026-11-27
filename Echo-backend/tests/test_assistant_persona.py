import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.assistant_persona.infrastructure.persona_loader import load_echo_examples
from features.assistant_persona.public import (
    AssistantPersonaNotFoundError,
    get_assistant_persona,
)


class AssistantPersonaTests(unittest.TestCase):
    def test_echo_persona_v5_loads_with_examples_from_markdown(self):
        persona = get_assistant_persona("echo-persona-v5")

        self.assertEqual("Echo", persona.name)
        self.assertEqual("echo-persona-v5", persona.version)
        self.assertEqual("echo_default", persona.persona_id)
        self.assertIn("情感陪伴为核心", persona.role)
        self.assertIn("朋友或 AI 恋人", persona.role)
        self.assertIn("傲娇", persona.traits[0])
        self.assertEqual(len(persona.traits), 3)
        self.assertEqual(len(persona.conversation_principles), 6)
        self.assertTrue(any("像微信打字" in item for item in persona.conversation_principles))
        self.assertTrue(any("共同进步" in item for item in persona.conversation_principles))
        self.assertTrue(any("人类生活史" in item for item in persona.forbidden_claims))
        self.assertEqual(len(persona.dialogue_examples), 8)

    def test_sidecar_examples_are_available_for_eval(self):
        examples = load_echo_examples()
        self.assertEqual(len(examples), 8)
        self.assertTrue(all(user and reply for user, reply in examples))
        self.assertTrue(any("\n" in reply for _, reply in examples))

    def test_unknown_persona_version_is_rejected(self):
        for version in ("missing-persona", "echo-persona-v4", "echo-persona-v3"):
            with self.assertRaises(AssistantPersonaNotFoundError):
                get_assistant_persona(version)


if __name__ == "__main__":
    unittest.main()
