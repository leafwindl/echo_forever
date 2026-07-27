import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import settings
from shared.interface.dependencies import get_current_user, resolve_current_user_from_token
from shared.security import TokenService


class CurrentUserTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_secret = settings.auth_token_secret
        self.original_expiry = settings.auth_token_expires_seconds
        settings.auth_token_secret = "test-secret"
        settings.auth_token_expires_seconds = 3600

    def tearDown(self):
        settings.auth_token_secret = self.original_secret
        settings.auth_token_expires_seconds = self.original_expiry

    async def test_resolves_user_exclusively_from_bearer_token(self):
        token = TokenService(secret="test-secret", expires_in=3600).issue_token("user_token")

        user = await get_current_user(f"Bearer {token}")

        self.assertEqual(user.user_id, "user_token")

    async def test_rejects_missing_token(self):
        with self.assertRaises(HTTPException) as error:
            await get_current_user(None)

        self.assertEqual(error.exception.status_code, 401)

    def test_token_resolver_returns_none_for_absent_header(self):
        self.assertIsNone(resolve_current_user_from_token(None))

    def test_rejects_invalid_authorization_header(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user_from_token("Basic abc")

        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_invalid_token(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user_from_token("Bearer not-a-valid-token")

        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
