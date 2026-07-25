import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.persona.domain.entities import PersonaUpdate, build_user_persona
from features.persona.interface.router import persona_get, persona_reset, persona_update
from features.persona.interface.schemas import PersonaUpdateRequest
from shared.interface.dependencies import CurrentUser


class PersonaInterfaceTests(unittest.TestCase):
    def test_request_schema_does_not_accept_user_identity_field(self):
        self.assertNotIn("user_id", PersonaUpdateRequest.model_fields)

    @patch("features.persona.interface.router.get_persona")
    def test_get_uses_authenticated_user(self, mock_get_persona):
        mock_get_persona.return_value = build_user_persona(
            "user-token",
            PersonaUpdate(preferred_name="小叶"),
            is_customized=True,
        )

        response = persona_get(CurrentUser(user_id="user-token"))

        mock_get_persona.assert_called_once_with("user-token")
        self.assertEqual("小叶", response.preferred_name)

    @patch("features.persona.interface.router.update_persona")
    def test_update_uses_authenticated_user_and_whitelisted_fields(self, mock_update_persona):
        mock_update_persona.return_value = build_user_persona(
            "user-token",
            PersonaUpdate(reply_style="concise"),
            is_customized=True,
        )
        request = PersonaUpdateRequest(reply_style="concise")

        response = persona_update(request, CurrentUser(user_id="user-token"))

        called_user_id, called_update = mock_update_persona.call_args.args
        self.assertEqual("user-token", called_user_id)
        self.assertEqual("concise", called_update.reply_style)
        self.assertEqual("concise", response.reply_style)

    @patch("features.persona.interface.router.reset_persona")
    def test_reset_only_targets_authenticated_user(self, mock_reset_persona):
        mock_reset_persona.return_value = build_user_persona(
            "user-token",
            PersonaUpdate(),
            is_customized=False,
        )

        response = persona_reset(CurrentUser(user_id="user-token"))

        mock_reset_persona.assert_called_once_with("user-token")
        self.assertFalse(response.is_customized)


if __name__ == "__main__":
    unittest.main()
