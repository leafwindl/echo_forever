import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.admin.application.debug_admin import (
    AdminValidationError,
    ClearUserChatContext,
    ManageRuntimePrompt,
)


class FakeRuntimeSettingsRepository:
    def __init__(self):
        self.values = {}

    def get_value(self, key):
        return self.values.get(key)

    def set_value(self, key, value):
        self.values[key] = value


class FakeChatContextAdminRepository:
    def __init__(self):
        self.cleared_user_ids = []

    def clear_user_chat_context(self, user_id):
        self.cleared_user_ids.append(user_id)
        return 3, 1


class AdminFeatureTests(unittest.TestCase):
    def test_runtime_prompt_falls_back_to_default_prompt(self):
        use_case = ManageRuntimePrompt(
            runtime_settings=FakeRuntimeSettingsRepository(),
            default_system_prompt="default prompt",
        )

        result = use_case.get_system_prompt()

        self.assertEqual(result.content, "default prompt")
        self.assertEqual(result.source, "env")

    def test_runtime_prompt_can_be_updated(self):
        repository = FakeRuntimeSettingsRepository()
        use_case = ManageRuntimePrompt(
            runtime_settings=repository,
            default_system_prompt="default prompt",
        )

        result = use_case.update_system_prompt("  new prompt  ")

        self.assertEqual(result.content, "new prompt")
        self.assertEqual(result.source, "runtime_settings")
        self.assertEqual(repository.values["system_prompt"], "new prompt")

    def test_runtime_prompt_rejects_empty_prompt(self):
        use_case = ManageRuntimePrompt(
            runtime_settings=FakeRuntimeSettingsRepository(),
            default_system_prompt="default prompt",
        )

        with self.assertRaises(AdminValidationError):
            use_case.update_system_prompt("   ")

    def test_clear_user_chat_context_trims_user_id(self):
        repository = FakeChatContextAdminRepository()
        use_case = ClearUserChatContext(chat_context_repository=repository)

        result = use_case.execute(" user_a ")

        self.assertEqual(repository.cleared_user_ids, ["user_a"])
        self.assertEqual(result.deleted_messages, 3)
        self.assertEqual(result.reset_conversations, 1)


if __name__ == "__main__":
    unittest.main()
