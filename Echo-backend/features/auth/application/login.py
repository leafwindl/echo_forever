import hashlib
import logging
from typing import Optional

from features.auth.domain.entities import AuthError
from features.auth.domain.services import UserIdentityRepository, WeChatSessionClient

logger = logging.getLogger(__name__)


def _make_user_id(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


class LoginWithWeChatCode:
    def __init__(
        self,
        user_repository: UserIdentityRepository,
        wechat_session_client: WeChatSessionClient,
        wechat_configured: bool,
    ):
        self.user_repository = user_repository
        self.wechat_session_client = wechat_session_client
        self.wechat_configured = wechat_configured

    async def execute(self, code: str, client_id: Optional[str] = None) -> str:
        clean_code = code.strip()
        if not clean_code:
            raise AuthError("Missing WeChat login code")

        if not self.wechat_configured:
            logger.warning("WECHAT_APPID/WECHAT_SECRET missing; using deterministic dev login")
            dev_source_id = client_id.strip() if client_id else clean_code
            dev_openid = f"dev_openid_{hashlib.sha256(dev_source_id.encode('utf-8')).hexdigest()}"
            user_id = _make_user_id("dev", dev_openid)
            self.user_repository.upsert_user(user_id=user_id, openid=dev_openid)
            return user_id

        openid = await self.wechat_session_client.exchange_code_for_openid(clean_code)
        user_id = _make_user_id("wx", openid)
        self.user_repository.upsert_user(user_id=user_id, openid=openid)
        return user_id
