import asyncio
import hashlib
import hmac
import re
import secrets
import uuid

from features.auth.domain.entities import (
    AuthConfigurationError,
    AuthenticatedSession,
    AuthError,
    SmsChallenge,
)
from features.auth.domain.services import AuthRepository, SessionTokenIssuer, SmsProvider

_MAINLAND_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
_SIX_DIGIT_CODE_PATTERN = re.compile(r"^\d{6}$")


def normalize_mainland_phone(value: str) -> str:
    compact = re.sub(r"[\s()\-]", "", value.strip())
    if compact.startswith("0086"):
        compact = compact[4:]
    elif compact.startswith("+86"):
        compact = compact[3:]
    elif compact.startswith("86") and len(compact) == 13:
        compact = compact[2:]
    if not _MAINLAND_PHONE_PATTERN.fullmatch(compact):
        raise AuthError("AUTH_PHONE_INVALID", "手机号格式或地区暂不支持")
    return f"+86{compact}"


def mask_phone(phone: str) -> str:
    normalized = normalize_mainland_phone(phone)
    local = normalized[3:]
    return f"+86 {local[:3]}****{local[-4:]}"


def hash_sms_code(*, pepper: str, request_id: str, phone: str, code: str) -> str:
    if not pepper:
        raise AuthConfigurationError()
    message = f"{request_id}:{phone}:{code}".encode()
    return hmac.new(pepper.encode(), message, hashlib.sha256).hexdigest()


class PhoneAuthService:
    def __init__(
        self,
        *,
        repository: AuthRepository,
        sms_provider: SmsProvider,
        token_issuer: SessionTokenIssuer,
        sms_code_pepper: str,
        challenge_expires_in: int,
        resend_after: int,
        maximum_attempts: int,
        access_expires_in: int,
        refresh_expires_in: int,
        fixed_verification_code: str = "",
        internal_fixture_phones: frozenset[str] = frozenset(),
    ):
        self.repository = repository
        self.sms_provider = sms_provider
        self.token_issuer = token_issuer
        self.sms_code_pepper = sms_code_pepper
        self.challenge_expires_in = challenge_expires_in
        self.resend_after = resend_after
        self.maximum_attempts = maximum_attempts
        self.access_expires_in = access_expires_in
        self.refresh_expires_in = refresh_expires_in
        self.fixed_verification_code = fixed_verification_code.strip()
        self.internal_fixture_phones = internal_fixture_phones

    async def request_phone_code(
        self,
        *,
        phone: str,
        device_id: str,
        purpose: str,
    ) -> SmsChallenge:
        normalized_phone = normalize_mainland_phone(phone)
        if purpose != "login":
            raise AuthError("REQUEST_VALIDATION_FAILED", "请求字段不合法")

        code = self._new_verification_code()
        request_id = f"sms_{uuid.uuid4().hex}"
        code_hash = hash_sms_code(
            pepper=self.sms_code_pepper,
            request_id=request_id,
            phone=normalized_phone,
            code=code,
        )
        await asyncio.to_thread(
            self.repository.create_challenge,
            request_id=request_id,
            phone=normalized_phone,
            code_hash=code_hash,
            purpose=purpose,
            device_id=device_id,
            expires_in=self.challenge_expires_in,
            resend_after=self.resend_after,
        )
        try:
            await self.sms_provider.send_code(normalized_phone, code, request_id)
        except AuthError:
            await asyncio.to_thread(self.repository.invalidate_challenge, request_id)
            raise
        except Exception as exc:
            await asyncio.to_thread(self.repository.invalidate_challenge, request_id)
            raise AuthError("AUTH_SMS_PROVIDER_UNAVAILABLE", "短信服务暂不可用") from exc

        return SmsChallenge(
            request_id=request_id,
            expires_in=self.challenge_expires_in,
            resend_after=self.resend_after,
            phone_masked=mask_phone(normalized_phone),
        )

    def verify_phone_code(
        self,
        *,
        request_id: str,
        phone: str,
        code: str,
        device_id: str,
    ) -> AuthenticatedSession:
        normalized_phone = normalize_mainland_phone(phone)
        clean_code = code.strip()
        if not _SIX_DIGIT_CODE_PATTERN.fullmatch(clean_code):
            raise AuthError("REQUEST_VALIDATION_FAILED", "请求字段不合法")
        code_hash = hash_sms_code(
            pepper=self.sms_code_pepper,
            request_id=request_id,
            phone=normalized_phone,
            code=clean_code,
        )
        return self.repository.verify_challenge_and_create_session(
            request_id=request_id,
            phone=normalized_phone,
            code_hash=code_hash,
            device_id=device_id,
            maximum_attempts=self.maximum_attempts,
            access_expires_in=self.access_expires_in,
            refresh_expires_in=self.refresh_expires_in,
            onboarding_completed=normalized_phone in self.internal_fixture_phones,
            token_issuer=self.token_issuer,
        )

    def refresh_session(self, *, refresh_token: str, device_id: str) -> AuthenticatedSession:
        clean_token = refresh_token.strip()
        if not clean_token:
            raise AuthError("AUTH_REFRESH_INVALID", "刷新凭证无效")
        return self.repository.rotate_refresh_token(
            token_hash=self.token_issuer.hash_refresh_token(clean_token),
            device_id=device_id,
            access_expires_in=self.access_expires_in,
            refresh_expires_in=self.refresh_expires_in,
            token_issuer=self.token_issuer,
        )

    def logout(self, *, refresh_token: str, user_id: str, device_id: str) -> None:
        clean_token = refresh_token.strip()
        if not clean_token:
            return
        self.repository.revoke_refresh_family(
            token_hash=self.token_issuer.hash_refresh_token(clean_token),
            user_id=user_id,
            device_id=device_id,
        )

    def _new_verification_code(self) -> str:
        if self.fixed_verification_code:
            if not _SIX_DIGIT_CODE_PATTERN.fullmatch(self.fixed_verification_code):
                raise AuthConfigurationError()
            return self.fixed_verification_code
        return f"{secrets.randbelow(1_000_000):06d}"
