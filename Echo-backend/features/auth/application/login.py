import hashlib
import logging
from typing import Optional

from features.auth.domain.entities import AuthConfigurationError, AuthenticatedSession, AuthError
from features.auth.domain.services import AccessTokenService, UserIdentityRepository, WeChatSessionClient

logger = logging.getLogger(__name__)


def _make_user_id(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


class LoginWithWeChatCode:
    def __init__(
        self,
        user_repository: UserIdentityRepository,
        wechat_session_client: WeChatSessionClient,
        access_token_service: AccessTokenService,
        wechat_configured: bool,
        token_expires_in: int,
    ):
        self.user_repository = user_repository
        self.wechat_session_client = wechat_session_client
        self.access_token_service = access_token_service
        self.wechat_configured = wechat_configured
        self.token_expires_in = token_expires_in

    async def execute(self, code: str, client_id: Optional[str] = None) -> AuthenticatedSession:
        clean_code = code.strip()
        if not clean_code:
            raise AuthError("Missing WeChat login code")

        if not self.wechat_configured:
            logger.warning("WECHAT_APPID/WECHAT_SECRET missing; using deterministic dev login")
            dev_source_id = client_id.strip() if client_id else clean_code
            dev_openid = f"dev_openid_{hashlib.sha256(dev_source_id.encode('utf-8')).hexdigest()}"
            user_id = _make_user_id("dev", dev_openid)
            self.user_repository.upsert_user(user_id=user_id, openid=dev_openid)
            return self._create_session(user_id)

        openid = await self.wechat_session_client.exchange_code_for_openid(clean_code)
        user_id = _make_user_id("wx", openid)
        self.user_repository.upsert_user(user_id=user_id, openid=openid)
        return self._create_session(user_id)

    def _create_session(self, user_id: str) -> AuthenticatedSession:
        try:
            access_token = self.access_token_service.issue_token(user_id)
        except ValueError as exc:
            raise AuthConfigurationError("Auth token secret is not configured") from exc

        return AuthenticatedSession(
            user_id=user_id,
            access_token=access_token,
            expires_in=self.token_expires_in,
        )
