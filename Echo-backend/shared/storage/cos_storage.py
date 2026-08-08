from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from qcloud_cos import CosConfig, CosS3Client

from shared.config import settings


class CosStorageConfigurationError(ValueError):
    """Raised when COS is enabled without a complete, safe configuration."""


@dataclass(frozen=True)
class CosStorageConfig:
    bucket: str
    region: str
    secret_id: str
    secret_key: str
    custom_domain: str = ""
    private_read: bool = True
    object_prefix: str = "echo"
    signed_url_expires_seconds: int = 900
    timeout_seconds: int = 30

    def validate(self) -> None:
        required = {
            "COS_BUCKET": self.bucket,
            "COS_REGION": self.region,
            "COS_SECRET_ID": self.secret_id,
            "COS_SECRET_KEY": self.secret_key,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise CosStorageConfigurationError(
                "Missing required COS settings: " + ", ".join(missing)
            )
        if "/" in self.bucket or "://" in self.bucket:
            raise CosStorageConfigurationError("COS_BUCKET must be the full bucket name only")
        if "/" in self.region or "://" in self.region:
            raise CosStorageConfigurationError(
                "COS_REGION must be a region code such as ap-guangzhou"
            )
        if not 60 <= self.signed_url_expires_seconds <= 86400:
            raise CosStorageConfigurationError(
                "COS_SIGNED_URL_EXPIRES_SECONDS must be between 60 and 86400"
            )
        if not 1 <= self.timeout_seconds <= 120:
            raise CosStorageConfigurationError("COS_TIMEOUT_SECONDS must be between 1 and 120")
        normalize_cos_custom_domain(self.custom_domain)
        normalize_cos_object_prefix(self.object_prefix)


@dataclass(frozen=True)
class CosObjectMetadata:
    object_key: str
    content_length: int
    content_type: str
    etag: str


def normalize_cos_custom_domain(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https":
        raise CosStorageConfigurationError("COS_CUSTOM_DOMAIN must use HTTPS")
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise CosStorageConfigurationError("COS_CUSTOM_DOMAIN must contain only an HTTPS host")
    if parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    return parsed.hostname


def normalize_cos_object_prefix(value: str) -> str:
    prefix = value.strip().strip("/")
    if not prefix:
        return ""
    try:
        _validate_object_path(prefix, setting_name="COS_OBJECT_PREFIX")
    except ValueError as exc:
        raise CosStorageConfigurationError(str(exc)) from exc
    return prefix


def _validate_object_path(value: str, *, setting_name: str = "object key") -> None:
    if "\\" in value:
        raise ValueError(f"{setting_name} must use forward slashes")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{setting_name} contains an unsafe path segment")
    if not re.fullmatch(r"[^\x00-\x1f\x7f]+", value):
        raise ValueError(f"{setting_name} contains control characters")


class CosObjectStorage:
    """Small COS adapter for private objects and short-lived download URLs."""

    def __init__(self, config: CosStorageConfig, client: Any | None = None):
        config.validate()
        self.config = config
        self.bucket = config.bucket.strip()
        self.object_prefix = normalize_cos_object_prefix(config.object_prefix)
        if client is None:
            sdk_config = CosConfig(
                Region=config.region.strip(),
                SecretId=config.secret_id.strip(),
                SecretKey=config.secret_key.strip(),
                Scheme="https",
                Timeout=config.timeout_seconds,
                Domain=normalize_cos_custom_domain(config.custom_domain) or None,
            )
            client = CosS3Client(sdk_config)
        self.client = client

    def object_key(self, relative_key: str) -> str:
        candidate = relative_key.strip().strip("/")
        if not candidate:
            raise ValueError("COS object key must not be empty")
        _validate_object_path(candidate)
        if not self.object_prefix:
            return candidate
        if candidate == self.object_prefix or candidate.startswith(f"{self.object_prefix}/"):
            return candidate
        return f"{self.object_prefix}/{candidate}"

    def put_bytes(
        self,
        relative_key: str,
        content: bytes,
        content_type: str,
        *,
        cache_control: str | None = None,
    ) -> str:
        if not content:
            raise ValueError("COS upload content must not be empty")
        if not content_type.strip():
            raise ValueError("COS upload content type must not be empty")
        object_key = self.object_key(relative_key)
        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Body": content,
            "Key": object_key,
            "ContentType": content_type,
        }
        if cache_control:
            request["CacheControl"] = cache_control
        self.client.put_object(**request)
        return object_key

    def put_file(
        self,
        relative_key: str,
        file_path: str | Path,
        content_type: str,
        *,
        cache_control: str | None = None,
    ) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size <= 0:
            raise ValueError("COS upload file must not be empty")
        if not content_type.strip():
            raise ValueError("COS upload content type must not be empty")
        object_key = self.object_key(relative_key)
        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": object_key,
            "ContentType": content_type,
        }
        if cache_control:
            request["CacheControl"] = cache_control
        with path.open("rb") as body:
            request["Body"] = body
            self.client.put_object(**request)
        return object_key

    def head(self, relative_key: str) -> CosObjectMetadata:
        object_key = self.object_key(relative_key)
        response = self.client.head_object(Bucket=self.bucket, Key=object_key)
        headers = {str(key).lower(): value for key, value in response.items()}
        return CosObjectMetadata(
            object_key=object_key,
            content_length=int(headers.get("content-length", 0)),
            content_type=str(headers.get("content-type", "")),
            etag=str(headers.get("etag", "")).strip('"'),
        )

    def delete(self, relative_key: str) -> None:
        object_key = self.object_key(relative_key)
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def stream_bytes(
        self,
        relative_key: str,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("COS download chunk size must be positive")
        object_key = self.object_key(relative_key)
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        body = response["Body"]

        def iterator() -> Iterator[bytes]:
            try:
                yield from body.get_stream(chunk_size=chunk_size)
            finally:
                body.get_raw_stream().close()

        return iterator()

    def download_url(
        self,
        relative_key: str,
        expires_seconds: int | None = None,
        *,
        download_name: str | None = None,
    ) -> str:
        object_key = self.object_key(relative_key)
        response_params: dict[str, str] = {}
        if download_name is not None:
            candidate = download_name.strip()
            if not candidate or not re.fullmatch(r"[A-Za-z0-9._-]+", candidate):
                raise ValueError("COS download filename contains unsafe characters")
            response_params["response-content-disposition"] = (
                f'attachment; filename="{candidate}"'
            )
        if not self.config.private_read:
            url = self.client.get_object_url(Bucket=self.bucket, Key=object_key)
            if not response_params:
                return url
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}{urlencode(response_params)}"
        expires = (
            self.config.signed_url_expires_seconds if expires_seconds is None else expires_seconds
        )
        if not 60 <= expires <= 86400:
            raise ValueError("COS signed URL expiration must be between 60 and 86400 seconds")
        return self.client.get_presigned_url(
            Bucket=self.bucket,
            Key=object_key,
            Method="GET",
            Expired=expires,
            Params=response_params,
        )


def resolve_cos_credentials() -> tuple[str, str]:
    cos_secret_id = settings.cos_secret_id.strip()
    cos_secret_key = settings.cos_secret_key.strip()
    if bool(cos_secret_id) != bool(cos_secret_key):
        raise CosStorageConfigurationError(
            "COS_SECRET_ID and COS_SECRET_KEY must be configured together"
        )
    if cos_secret_id and cos_secret_key:
        return cos_secret_id, cos_secret_key
    if settings.cos_reuse_tencent_credentials:
        return settings.tencent_secret_id.strip(), settings.tencent_secret_key.strip()
    return "", ""


@lru_cache(maxsize=1)
def get_cos_object_storage() -> CosObjectStorage:
    if not settings.cos_enabled:
        raise CosStorageConfigurationError("COS is disabled; set COS_ENABLED=true first")
    secret_id, secret_key = resolve_cos_credentials()
    return CosObjectStorage(
        CosStorageConfig(
            bucket=settings.cos_bucket,
            region=settings.cos_region,
            secret_id=secret_id,
            secret_key=secret_key,
            custom_domain=settings.cos_custom_domain,
            private_read=settings.cos_private_read,
            object_prefix=settings.cos_object_prefix,
            signed_url_expires_seconds=settings.cos_signed_url_expires_seconds,
            timeout_seconds=settings.cos_timeout_seconds,
        )
    )
