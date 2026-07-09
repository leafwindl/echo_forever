from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    code: str
    client_id: Optional[str] = None


class LoginResponse(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int
