from features.auth.domain.entities import (
    AuthConfigurationError,
    AuthenticatedSession,
    AuthError,
    SmsChallenge,
)
from features.auth.infrastructure import postgres_repositories
from features.auth.infrastructure.container import get_phone_auth_service


async def send_phone_verification(
    *, phone: str, device_id: str, purpose: str
) -> SmsChallenge:
    return await get_phone_auth_service().request_phone_code(
        phone=phone,
        device_id=device_id,
        purpose=purpose,
    )


def verify_phone_verification(
    *, request_id: str, phone: str, code: str, device_id: str
) -> AuthenticatedSession:
    return get_phone_auth_service().verify_phone_code(
        request_id=request_id,
        phone=phone,
        code=code,
        device_id=device_id,
    )


def refresh_phone_session(*, refresh_token: str, device_id: str) -> AuthenticatedSession:
    return get_phone_auth_service().refresh_session(
        refresh_token=refresh_token,
        device_id=device_id,
    )


def logout_phone_session(*, refresh_token: str, user_id: str, device_id: str) -> None:
    get_phone_auth_service().logout(
        refresh_token=refresh_token,
        user_id=user_id,
        device_id=device_id,
    )


def ensure_user_identity(user_id: str, conn=None) -> None:
    postgres_repositories.upsert_user(user_id=user_id, conn=conn)


__all__ = [
    "AuthConfigurationError",
    "AuthenticatedSession",
    "AuthError",
    "SmsChallenge",
    "ensure_user_identity",
    "logout_phone_session",
    "refresh_phone_session",
    "send_phone_verification",
    "verify_phone_verification",
]
