from typing import Optional

from features.auth.application.login import LoginWithWeChatCode
from features.auth.infrastructure.adapters import HttpWeChatSessionClient, UserIdentityRepositoryAdapter
from shared.config import settings

_login_with_wechat_code_use_case: Optional[LoginWithWeChatCode] = None


def get_login_with_wechat_code_use_case() -> LoginWithWeChatCode:
    global _login_with_wechat_code_use_case
    if _login_with_wechat_code_use_case is None:
        _login_with_wechat_code_use_case = LoginWithWeChatCode(
            user_repository=UserIdentityRepositoryAdapter(),
            wechat_session_client=HttpWeChatSessionClient(),
            wechat_configured=bool(settings.wechat_appid and settings.wechat_secret),
        )
    return _login_with_wechat_code_use_case


def reset_auth_use_cases_for_tests() -> None:
    global _login_with_wechat_code_use_case
    _login_with_wechat_code_use_case = None
