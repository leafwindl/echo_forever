import logging

from fastapi import APIRouter, HTTPException, Request, status

from features.auth.interface.schemas import LoginRequest, LoginResponse
from features.auth.public import AuthConfigurationError, AuthError, login_with_wechat_code
from shared.config import settings
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request):
    """登录接口：真实环境用微信 code 换 openid，本地开发用 client_id 生成稳定 dev 用户。"""
    client_host = http_request.client.host if http_request.client else "unknown"
    try:
        request_limiter.consume(
            [
                RateLimitRule(
                    key=f"login:client:{client_host}",
                    requests=settings.login_rate_limit_requests,
                    window_seconds=settings.login_rate_limit_window_seconds,
                    daily_requests=settings.login_daily_request_limit,
                ),
                RateLimitRule(
                    key="login:global",
                    daily_requests=settings.global_daily_login_request_limit,
                ),
            ]
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录请求过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        session = await login_with_wechat_code(request.code, request.client_id)
    except AuthError as e:
        logger.warning("WeChat login failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录失败，请重试") from e
    except AuthConfigurationError as e:
        logger.error("Auth configuration error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="登录服务暂不可用",
        ) from e
    return LoginResponse(
        user_id=session.user_id,
        access_token=session.access_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
    )
