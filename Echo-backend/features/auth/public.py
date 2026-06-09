from typing import Optional

from features.auth.domain.entities import AuthError
from features.auth.infrastructure.container import get_login_with_wechat_code_use_case


async def login_with_wechat_code(code: str, client_id: Optional[str] = None) -> str:
    use_case = get_login_with_wechat_code_use_case()
    return await use_case.execute(code=code, client_id=client_id)


__all__ = ["AuthError", "login_with_wechat_code"]
