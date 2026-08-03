import hashlib
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.auth.application.phone_auth import normalize_mainland_phone
from features.auth.domain.entities import AuthError
from features.auth.interface.schemas import (
    LogoutRequest,
    PhoneLoginRequest,
    PhoneLoginResponse,
    RefreshLoginRequest,
    TokenResponse,
    VerifyLoginRequest,
    VerifyLoginResponse,
)
from features.auth.public import (
    logout_phone_session,
    refresh_phone_session,
    send_phone_verification,
    verify_phone_verification,
)

logger = logging.getLogger(__name__)
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


_ERROR_STATUS = {
    "AUTH_PHONE_INVALID": status.HTTP_400_BAD_REQUEST,
    "AUTH_SMS_RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    "AUTH_SMS_PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "AUTH_CHALLENGE_INVALID": status.HTTP_400_BAD_REQUEST,
    "AUTH_CODE_INVALID": status.HTTP_400_BAD_REQUEST,
    "AUTH_CODE_EXPIRED": status.HTTP_410_GONE,
    "AUTH_CODE_ATTEMPTS_EXCEEDED": status.HTTP_423_LOCKED,
    "AUTH_VERIFY_RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    "AUTH_REFRESH_INVALID": status.HTTP_401_UNAUTHORIZED,
    "AUTH_REFRESH_EXPIRED": status.HTTP_401_UNAUTHORIZED,
    "AUTH_REFRESH_REUSED": status.HTTP_401_UNAUTHORIZED,
    "AUTH_USER_DISABLED": status.HTTP_403_FORBIDDEN,
    "AUTH_REFRESH_RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    "AUTH_ACCESS_INVALID": status.HTTP_401_UNAUTHORIZED,
    "AUTH_SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
    "REQUEST_VALIDATION_FAILED": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _trace_request_id(request: Request) -> str:
    stored = getattr(request.state, "auth_request_id", None)
    if stored:
        return str(stored)
    candidate = request.headers.get("X-Request-ID", "").strip()
    try:
        request_id = str(uuid.UUID(candidate)) if candidate else str(uuid.uuid4())
    except ValueError:
        request_id = str(uuid.uuid4())
    request.state.auth_request_id = request_id
    return request_id


def _error_response(request: Request, error: AuthError) -> JSONResponse:
    headers = {"X-Request-ID": _trace_request_id(request)}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        status_code=_ERROR_STATUS.get(error.code, status.HTTP_503_SERVICE_UNAVAILABLE),
        content={
            "code": error.code,
            "detail": error.detail,
            "request_id": _trace_request_id(request),
        },
        headers=headers,
    )


class AuthContractRoute(APIRoute):
    """Apply the stable auth error envelope without changing legacy feature errors."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            _trace_request_id(request)
            try:
                response = await original_handler(request)
            except RequestValidationError:
                return _error_response(
                    request,
                    AuthError("REQUEST_VALIDATION_FAILED", "请求字段不合法"),
                )
            except AuthError as exc:
                return _error_response(request, exc)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return _error_response(
                        request,
                        AuthError("AUTH_ACCESS_INVALID", "访问凭证无效或已过期"),
                    )
                raise
            except Exception:
                logger.exception(
                    "Authentication service failed request_id=%s path=%s",
                    _trace_request_id(request),
                    request.url.path,
                )
                provider_error = request.url.path.endswith("/phone")
                return _error_response(
                    request,
                    AuthError(
                        "AUTH_SMS_PROVIDER_UNAVAILABLE"
                        if provider_error
                        else "AUTH_SERVICE_UNAVAILABLE",
                        "短信服务暂不可用" if provider_error else "认证服务暂不可用",
                    ),
                )
            response.headers["X-Request-ID"] = _trace_request_id(request)
            return response

        return contract_handler


router = APIRouter(tags=["auth"], route_class=AuthContractRoute)


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _opaque_rate_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _consume_rate_limit(rules: list[RateLimitRule], *, code: str, detail: str) -> None:
    try:
        request_limiter.consume(rules)
    except RateLimitExceeded as exc:
        raise AuthError(code, detail, retry_after=exc.retry_after_seconds) from exc


@router.post(
    "/login/phone",
    response_model=PhoneLoginResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_phone_login(body: PhoneLoginRequest, http_request: Request) -> PhoneLoginResponse:
    normalized_phone = normalize_mainland_phone(body.phone)
    phone_key = _opaque_rate_key(normalized_phone)
    device_id = str(body.device_id)
    _consume_rate_limit(
        [
            RateLimitRule(
                key=f"auth:sms:phone:{phone_key}",
                requests=settings.sms_rate_limit_phone_requests,
                window_seconds=settings.sms_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key=f"auth:sms:device:{_opaque_rate_key(device_id)}",
                requests=settings.sms_rate_limit_device_requests,
                window_seconds=settings.sms_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key=f"auth:sms:ip:{_opaque_rate_key(_client_host(http_request))}",
                requests=settings.sms_rate_limit_ip_requests,
                window_seconds=settings.sms_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key="auth:sms:global",
                daily_requests=settings.sms_global_daily_request_limit,
            ),
        ],
        code="AUTH_SMS_RATE_LIMITED",
        detail="验证码发送过于频繁，请稍后再试",
    )
    challenge = await send_phone_verification(
        phone=normalized_phone,
        device_id=device_id,
        purpose=body.purpose,
    )
    return PhoneLoginResponse(
        request_id=challenge.request_id,
        expires_in=challenge.expires_in,
        resend_after=challenge.resend_after,
        phone_masked=challenge.phone_masked,
    )


@router.post("/login/verify", response_model=VerifyLoginResponse)
def verify_phone_login(body: VerifyLoginRequest, http_request: Request) -> VerifyLoginResponse:
    device_id = str(body.device_id)
    _consume_rate_limit(
        [
            RateLimitRule(
                key=f"auth:verify:request:{_opaque_rate_key(body.request_id)}",
                requests=settings.auth_verify_rate_limit_requests,
                window_seconds=settings.auth_verify_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key=f"auth:verify:device:{_opaque_rate_key(device_id)}",
                requests=settings.auth_verify_rate_limit_requests,
                window_seconds=settings.auth_verify_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key=f"auth:verify:ip:{_opaque_rate_key(_client_host(http_request))}",
                requests=settings.auth_verify_rate_limit_requests * 2,
                window_seconds=settings.auth_verify_rate_limit_window_seconds,
            ),
        ],
        code="AUTH_VERIFY_RATE_LIMITED",
        detail="验证请求过于频繁，请稍后再试",
    )
    session = verify_phone_verification(
        request_id=body.request_id,
        phone=body.phone,
        code=body.code,
        device_id=device_id,
    )
    return VerifyLoginResponse(
        user_id=session.user_id,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        refresh_expires_in=session.refresh_expires_in,
        is_new_user=session.is_new_user,
    )


@router.post("/login/refresh", response_model=TokenResponse)
def refresh_login(body: RefreshLoginRequest, http_request: Request) -> TokenResponse:
    device_id = str(body.device_id)
    _consume_rate_limit(
        [
            RateLimitRule(
                key=f"auth:refresh:device:{_opaque_rate_key(device_id)}",
                requests=settings.auth_refresh_rate_limit_requests,
                window_seconds=settings.auth_refresh_rate_limit_window_seconds,
            ),
            RateLimitRule(
                key=f"auth:refresh:ip:{_opaque_rate_key(_client_host(http_request))}",
                requests=settings.auth_refresh_rate_limit_requests * 2,
                window_seconds=settings.auth_refresh_rate_limit_window_seconds,
            ),
        ],
        code="AUTH_REFRESH_RATE_LIMITED",
        detail="刷新请求过于频繁，请稍后再试",
    )
    session = refresh_phone_session(
        refresh_token=body.refresh_token,
        device_id=device_id,
    )
    return TokenResponse(
        user_id=session.user_id,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        refresh_expires_in=session.refresh_expires_in,
    )


@router.post("/login/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    body: LogoutRequest,
    current_user: CurrentUserDependency,
) -> Response:
    logout_phone_session(
        refresh_token=body.refresh_token,
        user_id=current_user.user_id,
        device_id=str(body.device_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
