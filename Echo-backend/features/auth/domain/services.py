from typing import Optional, Protocol


class UserIdentityRepository(Protocol):
    def upsert_user(self, user_id: str, openid: Optional[str] = None) -> None:
        ...


class WeChatSessionClient(Protocol):
    async def exchange_code_for_openid(self, code: str) -> str:
        ...


class AccessTokenService(Protocol):
    def issue_token(self, user_id: str) -> str:
        ...

    def verify_token(self, token: str) -> str:
        ...
