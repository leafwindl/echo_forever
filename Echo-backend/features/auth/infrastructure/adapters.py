import logging

from features.auth.application.phone_auth import mask_phone
from features.auth.domain.entities import AuthError
from features.auth.domain.services import SmsProvider

logger = logging.getLogger(__name__)


class LoggingSmsProvider(SmsProvider):
    """Local-only SMS delivery adapter; code output requires an explicit switch."""

    def __init__(self, *, log_verification_code: bool):
        self.log_verification_code = log_verification_code

    async def send_code(self, phone: str, code: str, request_id: str) -> None:
        if self.log_verification_code:
            logger.warning(
                "Development SMS delivery request_id=%s phone_masked=%s otp=%s",
                request_id,
                mask_phone(phone),
                code,
            )
        else:
            logger.info(
                "Development SMS delivery accepted request_id=%s phone_masked=%s",
                request_id,
                mask_phone(phone),
            )


class _ConfigurableVendorStub(SmsProvider):
    provider_name = "vendor"

    def __init__(self, *, stub_delivery_enabled: bool, logging_provider: LoggingSmsProvider):
        self.stub_delivery_enabled = stub_delivery_enabled
        self.logging_provider = logging_provider

    async def send_code(self, phone: str, code: str, request_id: str) -> None:
        if not self.stub_delivery_enabled:
            raise AuthError("AUTH_SMS_PROVIDER_UNAVAILABLE", "短信服务暂不可用")
        logger.warning(
            "%s SMS adapter is running in explicitly enabled stub mode request_id=%s",
            self.provider_name,
            request_id,
        )
        await self.logging_provider.send_code(phone, code, request_id)


class AliyunSmsProvider(_ConfigurableVendorStub):
    """Configuration boundary for the future Aliyun SMS SDK integration."""

    provider_name = "aliyun"


class TencentSmsProvider(_ConfigurableVendorStub):
    """Configuration boundary for the future Tencent Cloud SMS SDK integration."""

    provider_name = "tencent"


def build_sms_provider(
    *,
    provider_name: str,
    log_verification_code: bool,
    stub_delivery_enabled: bool,
) -> SmsProvider:
    logging_provider = LoggingSmsProvider(log_verification_code=log_verification_code)
    normalized_name = provider_name.strip().lower()
    if normalized_name == "log":
        return logging_provider
    if normalized_name == "aliyun":
        return AliyunSmsProvider(
            stub_delivery_enabled=stub_delivery_enabled,
            logging_provider=logging_provider,
        )
    if normalized_name == "tencent":
        return TencentSmsProvider(
            stub_delivery_enabled=stub_delivery_enabled,
            logging_provider=logging_provider,
        )
    raise AuthError("AUTH_SMS_PROVIDER_UNAVAILABLE", "短信服务暂不可用")

