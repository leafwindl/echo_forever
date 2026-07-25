from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    client_id: Optional[str] = Field(default=None, max_length=128)


class LoginResponse(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int
