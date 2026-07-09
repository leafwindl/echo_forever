import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class TokenError(ValueError):
    pass


def _base64_url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


@dataclass(frozen=True)
class TokenService:
    secret: str
    expires_in: int

    def issue_token(self, user_id: str) -> str:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise TokenError("Missing token subject")
        if not self.secret:
            raise TokenError("Auth token secret is not configured")

        now = int(time.time())
        payload = {
            "sub": clean_user_id,
            "iat": now,
            "exp": now + max(self.expires_in, 1),
        }
        payload_text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        encoded_payload = _base64_url_encode(payload_text.encode("utf-8"))
        signature = self._sign(encoded_payload)
        return f"{encoded_payload}.{signature}"

    def verify_token(self, token: str) -> str:
        clean_token = token.strip()
        if not clean_token:
            raise TokenError("Missing access token")
        if not self.secret:
            raise TokenError("Auth token secret is not configured")

        try:
            encoded_payload, signature = clean_token.split(".", 1)
        except ValueError as exc:
            raise TokenError("Invalid access token") from exc

        expected_signature = self._sign(encoded_payload)
        if not hmac.compare_digest(signature, expected_signature):
            raise TokenError("Invalid access token")

        try:
            payload = json.loads(_base64_url_decode(encoded_payload).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise TokenError("Invalid access token") from exc

        user_id = str(payload.get("sub", "")).strip()
        expires_at = int(payload.get("exp", 0))
        if not user_id:
            raise TokenError("Invalid access token")
        if expires_at < int(time.time()):
            raise TokenError("Access token expired")
        return user_id

    def _sign(self, encoded_payload: str) -> str:
        digest = hmac.new(
            self.secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _base64_url_encode(digest)
