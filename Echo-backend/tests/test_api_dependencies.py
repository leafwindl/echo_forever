import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import settings
from shared.interface.dependencies import resolve_current_user, resolve_current_user_from_token
from shared.security import TokenService


class ResolveCurrentUserTests(unittest.TestCase):
    def setUp(self):
        self.original_auth_token_secret = settings.auth_token_secret
        self.original_auth_token_expires_seconds = settings.auth_token_expires_seconds
        self.original_enable_legacy_user_id_auth = settings.enable_legacy_user_id_auth
        settings.auth_token_secret = "test-secret"
        settings.auth_token_expires_seconds = 3600
        settings.enable_legacy_user_id_auth = True

    def tearDown(self):
        settings.auth_token_secret = self.original_auth_token_secret
        settings.auth_token_expires_seconds = self.original_auth_token_expires_seconds
        settings.enable_legacy_user_id_auth = self.original_enable_legacy_user_id_auth

    def test_uses_body_user_id_for_legacy_clients(self):
        user = resolve_current_user(body_user_id="  user_a  ")

        self.assertEqual(user.user_id, "user_a")

    def test_accepts_matching_header_and_body_user_id(self):
        user = resolve_current_user(header_user_id="user_a", body_user_id="user_a")

        self.assertEqual(user.user_id, "user_a")

    def test_rejects_missing_user_id(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user()

        self.assertEqual(error.exception.status_code, 400)

    def test_rejects_conflicting_user_identity(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user(header_user_id="user_a", body_user_id="user_b")

        self.assertEqual(error.exception.status_code, 403)

    def test_resolves_user_from_bearer_token(self):
        token = TokenService(secret="test-secret", expires_in=3600).issue_token("user_token")

        user = resolve_current_user_from_token(f"Bearer {token}")

        self.assertEqual(user.user_id, "user_token")

    def test_rejects_invalid_authorization_header(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user_from_token("Basic abc")

        self.assertEqual(error.exception.status_code, 401)

    def test_can_disable_legacy_user_id_auth(self):
        settings.enable_legacy_user_id_auth = False

        with self.assertRaises(HTTPException) as error:
            resolve_current_user(body_user_id="user_a")

        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
