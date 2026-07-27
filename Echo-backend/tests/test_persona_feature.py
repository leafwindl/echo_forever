import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.persona.application.persona_management import PersonaManagementService
from features.persona.domain.entities import (
    PersonaUpdate,
    PersonaValidationError,
    UserPreferences,
    build_user_preferences,
)


class InMemoryPersonaRepository:
    def __init__(self):
        self.preferences: dict[str, UserPreferences] = {}
        self.fail_saves = False

    def get(self, user_id: str) -> UserPreferences | None:
        return self.preferences.get(user_id)

    def save(self, preferences: UserPreferences) -> UserPreferences:
        if self.fail_saves:
            raise RuntimeError("database unavailable")
        self.preferences[preferences.user_id] = preferences
        return preferences


class PersonaDomainTests(unittest.TestCase):
    def build_preferences(
        self,
        update: PersonaUpdate = PersonaUpdate(),
        *,
        is_customized: bool = False,
        onboarding_completed: bool = False,
    ) -> UserPreferences:
        return build_user_preferences(
            " user-a ",
            update,
            is_customized=is_customized,
            onboarding_completed=onboarding_completed,
        )

    def test_defaults_are_safe_and_require_onboarding(self):
        preferences = self.build_preferences()

        self.assertEqual("user-a", preferences.user_id)
        self.assertEqual("natural", preferences.reply_style)
        self.assertEqual("balanced", preferences.reply_length)
        self.assertEqual("natural", preferences.relationship_pace)
        self.assertEqual("contextual", preferences.affection_style)
        self.assertTrue(preferences.enabled)
        self.assertFalse(preferences.is_customized)
        self.assertFalse(preferences.onboarding_completed)

    def test_normalizes_optional_text_and_deduplicates_topics(self):
        preferences = self.build_preferences(
            PersonaUpdate(
                preferred_name="  小叶  ",
                avoid_topics=("家庭话题", "家庭话题", "  医疗建议  "),
                about_user="  喜欢直接交流  ",
            ),
            is_customized=True,
            onboarding_completed=True,
        )

        self.assertEqual("小叶", preferences.preferred_name)
        self.assertEqual(("家庭话题", "医疗建议"), preferences.avoid_topics)
        self.assertEqual("喜欢直接交流", preferences.about_user)
        self.assertTrue(preferences.onboarding_completed)

    def test_rejects_invalid_enum_and_oversized_fields(self):
        invalid_updates = (
            PersonaUpdate(reply_style="roleplay"),
            PersonaUpdate(relationship_pace="instant"),
            PersonaUpdate(about_user="我" * 301),
            PersonaUpdate(avoid_topics=tuple(f"话题{i}" for i in range(6))),
        )
        for update in invalid_updates:
            with self.subTest(update=update), self.assertRaises(PersonaValidationError):
                self.build_preferences(update)


class PersonaManagementTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryPersonaRepository()
        self.service = PersonaManagementService(self.repository)

    def test_update_completes_onboarding_without_crossing_users(self):
        saved = self.service.update(
            "user-a",
            PersonaUpdate(preferred_name="小叶", reply_length="short"),
        )

        self.assertEqual("小叶", saved.preferred_name)
        self.assertTrue(saved.is_customized)
        self.assertTrue(saved.onboarding_completed)
        self.assertFalse(self.service.get("user-b").is_customized)
        self.assertFalse(self.service.get("user-b").onboarding_completed)

    def test_initial_update_requires_a_preferred_name(self):
        with self.assertRaises(PersonaValidationError):
            self.service.update("user-a", PersonaUpdate())

        self.assertNotIn("user-a", self.repository.preferences)

    def test_completed_user_can_later_clear_preferred_name(self):
        self.service.update("user-a", PersonaUpdate(preferred_name="小叶"))

        updated = self.service.update("user-a", PersonaUpdate(preferred_name=None))

        self.assertIsNone(updated.preferred_name)
        self.assertTrue(updated.onboarding_completed)

    def test_reset_keeps_onboarding_completed(self):
        self.service.update("user-a", PersonaUpdate(preferred_name="小叶"))

        reset = self.service.reset("user-a")

        self.assertFalse(reset.is_customized)
        self.assertTrue(reset.onboarding_completed)
        self.assertIsNone(reset.preferred_name)
        self.assertEqual(reset, self.repository.preferences["user-a"])

    def test_reset_cannot_skip_initial_onboarding(self):
        reset = self.service.reset("user-a")

        self.assertFalse(reset.onboarding_completed)

    def test_failed_update_does_not_replace_existing_value(self):
        self.service.update("user-a", PersonaUpdate(preferred_name="旧称呼"))
        self.repository.fail_saves = True

        with self.assertRaises(RuntimeError):
            self.service.update("user-a", PersonaUpdate(preferred_name="新称呼"))

        self.assertEqual("旧称呼", self.repository.preferences["user-a"].preferred_name)


if __name__ == "__main__":
    unittest.main()
