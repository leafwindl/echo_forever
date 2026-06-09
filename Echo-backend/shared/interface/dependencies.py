from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request, status


@dataclass(frozen=True)
class CurrentUser:
    user_id: str


def _clean_user_id(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_current_user(
    *,
    header_user_id: Optional[str] = None,
    query_user_id: Optional[str] = None,
    body_user_id: Optional[str] = None,
) -> CurrentUser:
    """Resolve the request user from legacy inputs until token auth is introduced."""
    candidates = [
        _clean_user_id(header_user_id),
        _clean_user_id(query_user_id),
        _clean_user_id(body_user_id),
    ]
    candidates = [user_id for user_id in candidates if user_id]
    if not candidates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user_id")

    if len(set(candidates)) > 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conflicting user identity")

    return CurrentUser(user_id=candidates[0])


async def get_current_user(
    request: Request,
    x_echo_user_id: Optional[str] = Header(default=None, alias="X-Echo-User-Id"),
) -> CurrentUser:
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
