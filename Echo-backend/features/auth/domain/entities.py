from dataclasses import dataclass


class AuthError(ValueError):
    """Stable authentication-domain failure exposed by the HTTP adapter."""

    def __init__(self, code: str, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


class AuthConfigurationError(AuthError):
    """Authentication cannot run because deployment configuration is incomplete."""

    def __init__(self, detail: str = "认证服务暂不可用"):
        super().__init__("AUTH_SERVICE_UNAVAILABLE", detail)


@dataclass(frozen=True)
class AuthenticatedSession:
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    refresh_expires_in: int = 0
    is_new_user: bool = False


@dataclass(frozen=True)
class SmsChallenge:
    request_id: str
    expires_in: int
    resend_after: int
    phone_masked: str


@dataclass(frozen=True)
class RefreshTokenMaterial:
    token_id: str
    raw_token: str
    token_hash: str

