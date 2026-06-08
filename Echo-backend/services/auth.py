import hashlib
import logging
from typing import Optional

import httpx

from config import settings
from services.memory import upsert_user

logger = logging.getLogger(__name__)

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class AuthError(ValueError):
    """登录链路中的业务错误，路由层会转换成 HTTP 错误。"""

    pass


def _make_user_id(prefix: str, source_id: str) -> str:
    """把 openid/client_id 哈希成内部 user_id，避免在业务表中直接暴露原始身份标识。"""
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


async def login_with_wechat_code(code: str, client_id: Optional[str] = None) -> str:
    clean_code = code.strip()
    if not clean_code:
        raise AuthError("Missing WeChat login code")

    if not settings.wechat_appid or not settings.wechat_secret:
        # 开发环境常常没有真实微信密钥。此时优先使用前端持久化的 client_id，
        # 让同一台设备重复登录得到同一个 dev_ 用户，同时不同设备不会串记忆。
        logger.warning("WECHAT_APPID/WECHAT_SECRET missing; using deterministic dev login")
        dev_source_id = client_id.strip() if client_id else clean_code
        dev_openid = f"dev_openid_{hashlib.sha256(dev_source_id.encode('utf-8')).hexdigest()}"
        user_id = _make_user_id("dev", dev_openid)
        upsert_user(user_id=user_id, openid=dev_openid)
        return user_id

    # 生产/真实小程序路径：用 wx.login() 给到的一次性 code 换取 openid。
    # openid 是微信侧对同一用户在同一小程序下的稳定标识。
    params = {
        "appid": settings.wechat_appid,
        "secret": settings.wechat_secret,
        "js_code": clean_code,
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

    # 对外统一返回 wx_ 开头的内部 user_id，后续所有记忆和消息都按这个 ID 隔离。
    user_id = _make_user_id("wx", openid)
    upsert_user(user_id=user_id, openid=openid)
    return user_id
