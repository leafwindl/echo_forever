from collections.abc import Callable
from typing import Protocol

from features.auth.domain.entities import (
    AuthenticatedSession,
    RefreshTokenMaterial,
)


class SmsProvider(Protocol):
    async def send_code(self, phone: str, code: str, request_id: str) -> None:
        ...


class SessionTokenIssuer(Protocol):
    def issue_access_token(self, user_id: str) -> str:
        ...

    def new_refresh_token(self) -> RefreshTokenMaterial:
        ...

    def hash_refresh_token(self, token: str) -> str:
        ...


class AuthRepository(Protocol):
    def create_challenge(
        self,
        *,
        request_id: str,
        phone: str,
        code_hash: str,
        purpose: str,
        device_id: str,
        expires_in: int,
        resend_after: int,
    ) -> None:
        ...

    def invalidate_challenge(self, request_id: str) -> None:
        ...

    def verify_challenge_and_create_session(
        self,
        *,
        request_id: str,
        phone: str,
        code_hash: str,
        device_id: str,
        maximum_attempts: int,
        access_expires_in: int,
        refresh_expires_in: int,
        onboarding_completed: bool,
        token_issuer: SessionTokenIssuer,
    ) -> AuthenticatedSession:
        ...

    def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        device_id: str,
        access_expires_in: int,
        refresh_expires_in: int,
        token_issuer: SessionTokenIssuer,
    ) -> AuthenticatedSession:
        ...

    def revoke_refresh_family(self, *, token_hash: str, user_id: str, device_id: str) -> None:
        ...

    def upsert_user(self, user_id: str) -> None:
        ...


AccessTokenFactory = Callable[[str], str]

