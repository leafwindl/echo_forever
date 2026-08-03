from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from shared.config import settings
from shared.security import TokenError, TokenService, parse_verification_keys


@dataclass(frozen=True)
class CurrentUser:
    user_id: str


def _clean_user_id(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _token_service() -> TokenService:
    return TokenService(
        secret=settings.auth_token_secret,
        expires_in=settings.auth_token_expires_seconds,
        issuer=settings.auth_jwt_issuer,
        audience=settings.auth_jwt_audience,
        key_id=settings.auth_jwt_key_id,
        verification_keys=parse_verification_keys(settings.auth_jwt_previous_keys_json),
    )


def resolve_current_user_from_token(authorization: str | None) -> CurrentUser | None:
    clean_authorization = _clean_user_id(authorization)
    if not clean_authorization:
        return None
    scheme, _, token = clean_authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )

    try:
        user_id = _token_service().verify_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return CurrentUser(user_id=user_id)


async def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CurrentUser:
    """Resolve the current user exclusively from a signed Bearer token."""
    current_user = resolve_current_user_from_token(authorization)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    return current_user
