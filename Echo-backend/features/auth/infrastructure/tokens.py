import hashlib
import hmac
import secrets
import uuid

from shared.security import TokenError, TokenService

from features.auth.domain.entities import AuthConfigurationError, RefreshTokenMaterial
from features.auth.domain.services import SessionTokenIssuer


class AuthSessionTokenIssuer(SessionTokenIssuer):
    def __init__(self, *, access_token_service: TokenService, refresh_token_pepper: str):
        self.access_token_service = access_token_service
        self.refresh_token_pepper = refresh_token_pepper

    def issue_access_token(self, user_id: str) -> str:
        try:
            return self.access_token_service.issue_token(user_id)
        except TokenError as exc:
            raise AuthConfigurationError() from exc

    def new_refresh_token(self) -> RefreshTokenMaterial:
        raw_token = secrets.token_urlsafe(32)
        return RefreshTokenMaterial(
            token_id=f"rt_{uuid.uuid4().hex}",
            raw_token=raw_token,
            token_hash=self.hash_refresh_token(raw_token),
        )

    def hash_refresh_token(self, token: str) -> str:
        if not self.refresh_token_pepper:
            raise AuthConfigurationError()
        return hmac.new(
            self.refresh_token_pepper.encode(),
            token.encode(),
            hashlib.sha256,
        ).hexdigest()

