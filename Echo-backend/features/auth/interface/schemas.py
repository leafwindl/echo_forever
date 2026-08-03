from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PhoneLoginRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)
    device_id: UUID
    purpose: Literal["login"]


class PhoneLoginResponse(BaseModel):
    request_id: str
    expires_in: int
    resend_after: int
    phone_masked: str


class VerifyLoginRequest(BaseModel):
    request_id: str = Field(min_length=5, max_length=80)
    phone: str = Field(min_length=5, max_length=32)
    code: str = Field(pattern=r"^\d{6}$")
    device_id: UUID


class TokenResponse(BaseModel):
    user_id: str
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_expires_in: int


class VerifyLoginResponse(TokenResponse):
    is_new_user: bool


class RefreshLoginRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)
    device_id: UUID


class LogoutRequest(RefreshLoginRequest):
    pass


class AuthErrorResponse(BaseModel):
    code: str
    detail: str
    request_id: str

