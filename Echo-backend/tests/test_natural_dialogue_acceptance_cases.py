import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.persona.domain.entities import PersonaUpdate, build_user_persona

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "natural_dialogue_acceptance_cases.json"


class NaturalDialogueAcceptanceCasesTests(unittest.TestCase):
    def test_internal_acceptance_set_has_20_unique_cases(self):
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        for case in cases:
            self.assertTrue(case["user_message"].strip())
            self.assertTrue(case["expected"].strip())

    def test_fixture_persona_values_follow_domain_contract(self):
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        for case in cases:
            raw_persona = case.get("persona")
            if not raw_persona:
                continue
            build_user_persona(
                f"fixture-{case['id']}",
                PersonaUpdate(
                    preferred_name=raw_persona.get("preferred_name"),
                    reply_style=raw_persona.get("reply_style", "natural"),
                    reply_length=raw_persona.get("reply_length", "balanced"),
                    support_mode=raw_persona.get("support_mode", "balanced"),
                    proactivity=raw_persona.get("proactivity", "balanced"),
                    avoid_topics=tuple(raw_persona.get("avoid_topics", [])),
                    about_user=raw_persona.get("about_user"),
                    enabled=raw_persona.get("enabled", True),
                ),
                is_customized=True,
            )


if __name__ == "__main__":
    unittest.main()
