from shared.config import settings
from shared.security import TokenService, parse_verification_keys

from features.auth.application.phone_auth import PhoneAuthService, normalize_mainland_phone
from features.auth.infrastructure.adapters import build_sms_provider
from features.auth.infrastructure.postgres_repositories import PostgresAuthRepository
from features.auth.infrastructure.tokens import AuthSessionTokenIssuer

_phone_auth_service: PhoneAuthService | None = None


def get_phone_auth_service() -> PhoneAuthService:
    global _phone_auth_service
    if _phone_auth_service is None:
        access_token_service = TokenService(
            secret=settings.auth_token_secret,
            expires_in=settings.auth_token_expires_seconds,
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            key_id=settings.auth_jwt_key_id,
            verification_keys=parse_verification_keys(settings.auth_jwt_previous_keys_json),
        )
        token_issuer = AuthSessionTokenIssuer(
            access_token_service=access_token_service,
            refresh_token_pepper=(
                settings.auth_refresh_token_pepper or settings.auth_token_secret
            ),
        )
        fixture_phones = frozenset(
            normalize_mainland_phone(phone)
            for phone in settings.auth_internal_fixture_phones.split(",")
            if phone.strip()
        )
        _phone_auth_service = PhoneAuthService(
            repository=PostgresAuthRepository(),
            sms_provider=build_sms_provider(
                provider_name=settings.sms_provider,
                log_verification_code=settings.sms_log_verification_code,
                stub_delivery_enabled=settings.sms_stub_delivery_enabled,
            ),
            token_issuer=token_issuer,
            sms_code_pepper=settings.sms_code_pepper or settings.auth_token_secret,
            challenge_expires_in=settings.sms_challenge_expires_seconds,
            resend_after=settings.sms_resend_after_seconds,
            maximum_attempts=settings.sms_maximum_attempts,
            access_expires_in=settings.auth_token_expires_seconds,
            refresh_expires_in=settings.auth_refresh_token_expires_seconds,
            fixed_verification_code=settings.sms_fixed_verification_code,
            internal_fixture_phones=fixture_phones,
        )
    return _phone_auth_service


def reset_auth_use_cases_for_tests() -> None:
    global _phone_auth_service
    _phone_auth_service = None

