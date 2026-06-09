import logging
from typing import Optional

import httpx

from features.auth.domain.entities import AuthError
from features.auth.domain.services import UserIdentityRepository, WeChatSessionClient
from repositories.user_repository import upsert_user
from shared.config import settings

logger = logging.getLogger(__name__)

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class UserIdentityRepositoryAdapter(UserIdentityRepository):
    def upsert_user(self, user_id: str, openid: Optional[str] = None) -> None:
        upsert_user(user_id=user_id, openid=openid)


class HttpWeChatSessionClient(WeChatSessionClient):
    async def exchange_code_for_openid(self, code: str) -> str:
        params = {
            "appid": settings.wechat_appid,
            "secret": settings.wechat_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.timeout) as client:
                response = await client.get(WECHAT_CODE2SESSION_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error("WeChat code2session request failed: %s", exc)
            raise AuthError("WeChat login request failed") from exc

        openid: Optional[str] = data.get("openid")
        if not openid:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "unknown error")
            logger.error("WeChat code2session failed: errcode=%s errmsg=%s", errcode, errmsg)
            raise AuthError(f"WeChat login failed: {errmsg}")
        return openid
