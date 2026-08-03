import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field


class TokenError(ValueError):
    pass


def _base64_url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def parse_verification_keys(value: str) -> dict[str, str]:
    """Parse a JSON kid-to-secret map used while JWT signing keys are rotated."""
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TokenError("Invalid JWT verification key configuration") from exc
    if not isinstance(parsed, dict):
        raise TokenError("Invalid JWT verification key configuration")
    keys = {str(key).strip(): str(secret) for key, secret in parsed.items()}
    if any(not key or not secret for key, secret in keys.items()):
        raise TokenError("Invalid JWT verification key configuration")
    return keys


@dataclass(frozen=True)
class TokenService:
    """Minimal standards-compliant HS256 JWT issuer/verifier for access tokens."""

    secret: str
    expires_in: int
    issuer: str = "echo-backend"
    audience: str = "echo-app"
    key_id: str = "echo-v1"
    verification_keys: Mapping[str, str] = field(default_factory=dict)

    def issue_token(self, user_id: str) -> str:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise TokenError("Missing token subject")
        if not self.secret:
            raise TokenError("Auth token secret is not configured")

        now = int(time.time())
        header = {"alg": "HS256", "kid": self.key_id, "typ": "JWT"}
        payload = {
            "aud": self.audience,
            "exp": now + max(self.expires_in, 1),
            "iat": now,
            "iss": self.issuer,
            "jti": uuid.uuid4().hex,
            "sub": clean_user_id,
            "typ": "access",
        }
        encoded_header = _encode_json_segment(header)
        encoded_payload = _encode_json_segment(payload)
        signing_input = f"{encoded_header}.{encoded_payload}"
        signature = self._sign(signing_input, self.secret)
        return f"{signing_input}.{signature}"

    def verify_token(self, token: str) -> str:
        clean_token = token.strip()
        if not clean_token:
            raise TokenError("Missing access token")

        parts = clean_token.split(".")
        if len(parts) != 3 or not all(parts):
            raise TokenError("Invalid access token")
        encoded_header, encoded_payload, signature = parts

        header = _decode_json_segment(encoded_header)
        payload = _decode_json_segment(encoded_payload)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise TokenError("Invalid access token")

        key_id = str(header.get("kid", "")).strip()
        verification_secret = self._secret_for_key_id(key_id)
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = self._sign(signing_input, verification_secret)
        if not hmac.compare_digest(signature, expected_signature):
            raise TokenError("Invalid access token")

        now = int(time.time())
        try:
            issued_at = int(payload.get("iat", 0))
            expires_at = int(payload.get("exp", 0))
        except (TypeError, ValueError) as exc:
            raise TokenError("Invalid access token") from exc

        user_id = str(payload.get("sub", "")).strip()
        if (
            not user_id
            or payload.get("typ") != "access"
            or payload.get("iss") != self.issuer
            or not _audience_matches(payload.get("aud"), self.audience)
            or not str(payload.get("jti", "")).strip()
            or issued_at <= 0
            or issued_at > now + 60
        ):
            raise TokenError("Invalid access token")
        if expires_at <= now:
            raise TokenError("Access token expired")
        return user_id

    def _secret_for_key_id(self, key_id: str) -> str:
        if key_id == self.key_id and self.secret:
            return self.secret
        previous_secret = self.verification_keys.get(key_id)
        if not key_id or not previous_secret:
            raise TokenError("Invalid access token")
        return previous_secret

    @staticmethod
    def _sign(signing_input: str, secret: str) -> str:
        digest = hmac.new(
            secret.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _base64_url_encode(digest)


def _encode_json_segment(value: dict[str, object]) -> str:
    raw = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return _base64_url_encode(raw.encode("utf-8"))


def _decode_json_segment(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(_base64_url_decode(value).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenError("Invalid access token") from exc
    if not isinstance(decoded, dict):
        raise TokenError("Invalid access token")
    return decoded


def _audience_matches(claim: object, expected: str) -> bool:
    if isinstance(claim, str):
        return hmac.compare_digest(claim, expected)
    if isinstance(claim, list):
        return any(isinstance(item, str) and hmac.compare_digest(item, expected) for item in claim)
    return False
