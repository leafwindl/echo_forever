from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from shared.config import settings
from shared.security import TokenError, TokenService


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


async def get_bearer_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CurrentUser:
    """Require Bearer authentication even when legacy development auth is enabled."""
    current_user = resolve_current_user_from_token(authorization)
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    return current_user


def resolve_current_user(
    *,
    header_user_id: str | None = None,
    query_user_id: str | None = None,
    body_user_id: str | None = None,
) -> CurrentUser:
    """Resolve the request user from legacy inputs while compatibility is enabled."""
    if not settings.enable_legacy_user_id_auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    candidates = [
        _clean_user_id(header_user_id),
        _clean_user_id(query_user_id),
        _clean_user_id(body_user_id),
    ]
    candidates = [user_id for user_id in candidates if user_id]
    if not candidates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user_id")

    if len(set(candidates)) > 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conflicting user identity",
        )

    return CurrentUser(user_id=candidates[0])


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_echo_user_id: str | None = Header(default=None, alias="X-Echo-User-Id"),
) -> CurrentUser:
    token_user = resolve_current_user_from_token(authorization)
    if token_user:
        return token_user

    body_user_id = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                body_user_id = body.get("user_id")

    return resolve_current_user(
        header_user_id=x_echo_user_id,
        query_user_id=request.query_params.get("user_id"),
        body_user_id=body_user_id,
    )
