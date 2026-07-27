from typing import Optional

from features.auth.domain.entities import AuthConfigurationError, AuthenticatedSession, AuthError
from features.auth.infrastructure.container import get_login_with_wechat_code_use_case
from features.auth.infrastructure import postgres_repositories


async def login_with_wechat_code(code: str, client_id: Optional[str] = None) -> AuthenticatedSession:
    use_case = get_login_with_wechat_code_use_case()
    return await use_case.execute(code=code, client_id=client_id)


def ensure_user_identity(user_id: str, conn=None) -> None:
    postgres_repositories.upsert_user(user_id=user_id, conn=conn)


__all__ = [
    "AuthConfigurationError",
    "AuthenticatedSession",
    "AuthError",
    "ensure_user_identity",
    "login_with_wechat_code",
]
