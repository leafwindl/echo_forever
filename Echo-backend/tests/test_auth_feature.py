import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.postgres_schema import build_postgres_schema_text
from features.auth.application.phone_auth import mask_phone, normalize_mainland_phone
from features.auth.domain.entities import AuthenticatedSession, AuthError, SmsChallenge
from features.auth.interface.router import router
from shared.security import TokenService

DEVICE_ID = "76e8584a-1c97-43eb-a560-555eaabeaca9"


def _decode_segment(value: str) -> dict[str, object]:
    value += "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value).decode())


class AccessTokenContractTests(unittest.TestCase):
    def test_issues_standard_access_jwt_with_required_claims(self):
        service = TokenService(
            secret="test-secret",
            expires_in=900,
            issuer="echo-backend",
            audience="echo-app",
            key_id="test-v1",
        )

        token = service.issue_token("phone_user")
        header, payload, signature = token.split(".")

        self.assertTrue(signature)
        self.assertEqual(_decode_segment(header)["kid"], "test-v1")
        claims = _decode_segment(payload)
        self.assertEqual(claims["sub"], "phone_user")
        self.assertEqual(claims["typ"], "access")
        self.assertEqual(claims["iss"], "echo-backend")
        self.assertEqual(claims["aud"], "echo-app")
        self.assertTrue(claims["jti"])
        self.assertEqual(service.verify_token(token), "phone_user")

    def test_accepts_previous_key_only_when_kid_is_configured(self):
        old = TokenService(secret="old-secret", expires_in=900, key_id="old-v1")
        token = old.issue_token("phone_user")
        current = TokenService(
            secret="new-secret",
            expires_in=900,
            key_id="new-v1",
            verification_keys={"old-v1": "old-secret"},
        )

        self.assertEqual(current.verify_token(token), "phone_user")


class PhoneContractTests(unittest.TestCase):
    def test_normalizes_supported_mainland_forms(self):
        self.assertEqual(normalize_mainland_phone("138 0013 8000"), "+8613800138000")
        self.assertEqual(normalize_mainland_phone("0086-13800138000"), "+8613800138000")
        self.assertEqual(mask_phone("+8613800138000"), "+86 138****8000")

    def test_rejects_unsupported_phone(self):
        with self.assertRaises(AuthError) as error:
            normalize_mainland_phone("+12025550123")
        self.assertEqual(error.exception.code, "AUTH_PHONE_INVALID")

    def test_schema_freezes_phone_challenge_and_rotation_tables(self):
        schema = build_postgres_schema_text(vector_dimension=1024)
        self.assertIn("phone TEXT UNIQUE", schema)
        self.assertIn("phone_verified_at TIMESTAMPTZ", schema)
        self.assertNotIn("openid TEXT", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS sms_verification_challenges", schema)
        self.assertIn("code_hash TEXT NOT NULL", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS auth_refresh_tokens", schema)
        self.assertIn("token_family_id TEXT NOT NULL", schema)
        self.assertIn("replaced_by TEXT", schema)


class AuthHttpContractTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_old_wechat_login_is_disabled(self):
        response = self.client.post("/login", json={"code": "legacy"})
        self.assertEqual(response.status_code, 404)

    def test_phone_challenge_contract_and_request_id_echo(self):
        trace_id = "4b3f9b2b-2a42-4ff2-b923-23b653ef289d"
        challenge = SmsChallenge(
            request_id="sms_test",
            expires_in=300,
            resend_after=60,
            phone_masked="+86 138****8000",
        )
        with patch(
            "features.auth.interface.router.send_phone_verification",
            new=AsyncMock(return_value=challenge),
        ):
            response = self.client.post(
                "/login/phone",
                headers={"X-Request-ID": trace_id},
                json={
                    "phone": "+8613800138000",
                    "device_id": DEVICE_ID,
                    "purpose": "login",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers["X-Request-ID"], trace_id)
        self.assertEqual(
            response.json(),
            {
                "request_id": "sms_test",
                "expires_in": 300,
                "resend_after": 60,
                "phone_masked": "+86 138****8000",
            },
        )

    def test_validation_failure_uses_stable_error_envelope(self):
        response = self.client.post(
            "/login/phone",
            json={"phone": "bad", "device_id": "bad", "purpose": "other"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "REQUEST_VALIDATION_FAILED")
        self.assertTrue(response.json()["request_id"])

    def test_verify_contract(self):
        session = AuthenticatedSession(
            user_id="phone_user",
            access_token="access.jwt.value",
            refresh_token="refresh-value",
            expires_in=900,
            refresh_expires_in=2592000,
            is_new_user=True,
        )
        with patch(
            "features.auth.interface.router.verify_phone_verification",
            return_value=session,
        ):
            response = self.client.post(
                "/login/verify",
                json={
                    "request_id": "sms_test",
                    "phone": "+8613800138000",
                    "code": "482731",
                    "device_id": DEVICE_ID,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token_type"], "bearer")
        self.assertEqual(response.json()["is_new_user"], True)
        self.assertEqual(response.json()["refresh_expires_in"], 2592000)

    def test_refresh_reuse_error_contract(self):
        with patch(
            "features.auth.interface.router.refresh_phone_session",
            side_effect=AuthError("AUTH_REFRESH_REUSED", "检测到刷新凭证重放"),
        ):
            response = self.client.post(
                "/login/refresh",
                json={"refresh_token": "old-token", "device_id": DEVICE_ID},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "AUTH_REFRESH_REUSED")


if __name__ == "__main__":
    unittest.main()
