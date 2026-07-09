from dataclasses import dataclass


class AuthError(ValueError):
    """Business error for the login flow."""

    pass


class AuthConfigurationError(RuntimeError):
    """Raised when authentication cannot run because deployment config is missing."""


@dataclass(frozen=True)
class AuthenticatedSession:
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0
