from fastapi import APIRouter, HTTPException, status

from features.auth.interface.schemas import LoginRequest, LoginResponse
from features.auth.public import AuthConfigurationError, AuthError, login_with_wechat_code

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """登录接口：真实环境用微信 code 换 openid，本地开发用 client_id 生成稳定 dev 用户。"""
    try:
        session = await login_with_wechat_code(request.code, request.client_id)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except AuthConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    return LoginResponse(
        user_id=session.user_id,
        access_token=session.access_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
    )
