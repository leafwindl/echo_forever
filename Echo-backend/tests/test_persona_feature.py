import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.persona.application.persona_management import PersonaManagementService
from features.persona.domain.entities import (
    PersonaUpdate,
    PersonaValidationError,
    UserPersona,
    build_user_persona,
)


class InMemoryPersonaRepository:
    def __init__(self):
        self.personas: dict[str, UserPersona] = {}
        self.fail_saves = False

    def get(self, user_id: str) -> UserPersona | None:
        return self.personas.get(user_id)

    def save(self, persona: UserPersona) -> UserPersona:
        if self.fail_saves:
            raise RuntimeError("database unavailable")
        self.personas[persona.user_id] = persona
        return persona

    def delete(self, user_id: str) -> bool:
        return self.personas.pop(user_id, None) is not None


class PersonaDomainTests(unittest.TestCase):
    def test_defaults_are_safe_and_not_customized(self):
        persona = build_user_persona(" user-a ", PersonaUpdate(), is_customized=False)

        self.assertEqual("user-a", persona.user_id)
        self.assertEqual("natural", persona.reply_style)
        self.assertEqual("balanced", persona.reply_length)
        self.assertTrue(persona.enabled)
        self.assertFalse(persona.is_customized)

    def test_normalizes_optional_text_and_deduplicates_topics(self):
        persona = build_user_persona(
            "user-a",
            PersonaUpdate(
                preferred_name="  小叶  ",
                avoid_topics=("家庭话题", "家庭话题", "  医疗建议  "),
                about_user="  喜欢直接交流  ",
            ),
            is_customized=True,
        )

        self.assertEqual("小叶", persona.preferred_name)
        self.assertEqual(("家庭话题", "医疗建议"), persona.avoid_topics)
        self.assertEqual("喜欢直接交流", persona.about_user)

    def test_rejects_invalid_enum_and_oversized_fields(self):
        with self.assertRaises(PersonaValidationError):
            build_user_persona(
                "user-a",
                PersonaUpdate(reply_style="roleplay"),
                is_customized=True,
            )
        with self.assertRaises(PersonaValidationError):
            build_user_persona(
                "user-a",
                PersonaUpdate(about_user="我" * 301),
                is_customized=True,
            )
        with self.assertRaises(PersonaValidationError):
            build_user_persona(
                "user-a",
                PersonaUpdate(avoid_topics=tuple(f"话题{i}" for i in range(6))),
                is_customized=True,
            )


class PersonaManagementTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryPersonaRepository()
        self.service = PersonaManagementService(self.repository)

    def test_create_update_and_reset_do_not_cross_users(self):
        saved = self.service.update(
            "user-a",
            PersonaUpdate(preferred_name="小叶", reply_length="short"),
        )

        self.assertEqual("小叶", saved.preferred_name)
        self.assertTrue(saved.is_customized)
        self.assertFalse(self.service.get("user-b").is_customized)
        self.assertIsNone(self.service.get("user-b").preferred_name)

        reset = self.service.reset("user-a")
        self.assertFalse(reset.is_customized)
        self.assertIsNone(reset.preferred_name)
        self.assertNotIn("user-a", self.repository.personas)

    def test_failed_update_does_not_replace_existing_value(self):
        self.service.update("user-a", PersonaUpdate(preferred_name="旧称呼"))
        self.repository.fail_saves = True

        with self.assertRaises(RuntimeError):
            self.service.update("user-a", PersonaUpdate(preferred_name="新称呼"))

        self.assertEqual("旧称呼", self.repository.personas["user-a"].preferred_name)


if __name__ == "__main__":
    unittest.main()
