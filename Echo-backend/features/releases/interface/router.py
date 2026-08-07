from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from shared.config import settings
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter
from shared.storage import CosObjectStorage, get_cos_object_storage

from features.releases.domain.entities import AppRelease
from features.releases.infrastructure.postgres_repository import PostgresReleaseRepository
from features.releases.interface.schemas import (
    LatestReleaseResponse,
    ReleaseDownloadRequest,
    ReleaseDownloadResponse,
    ReleaseResponse,
)

router = APIRouter(prefix="/releases", tags=["releases"])


def get_release_repository() -> PostgresReleaseRepository:
    return PostgresReleaseRepository()


def _client_host(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _consume_rate_limit(request: Request, action: str) -> None:
    opaque_ip = hashlib.sha256(_client_host(request).encode()).hexdigest()[:24]
    try:
        request_limiter.consume(
            [
                RateLimitRule(
                    key=f"releases:{action}:ip:{opaque_ip}",
                    requests=settings.release_rate_limit_requests,
                    window_seconds=settings.release_rate_limit_window_seconds,
                )
            ]
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many release requests",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def _response(release: AppRelease, current_version_code: int) -> ReleaseResponse:
    return ReleaseResponse(
        release_id=release.release_id,
        platform=release.platform,
        channel=release.channel,
        package_name=release.package_name,
        version_name=release.version_name,
        version_code=release.version_code,
        minimum_version_code=release.minimum_version_code,
        sha256=release.sha256,
        size_bytes=release.size_bytes,
        release_notes=list(release.release_notes),
        mandatory=release.is_mandatory_for(current_version_code),
        published_at=release.published_at,
    )


def _artifact_signature(release_id: str, expires_at: int) -> str:
    secret = settings.auth_token_secret.strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Release download signing is unavailable",
        )
    payload = f"release-artifact:{release_id}:{expires_at}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _artifact_url(request: Request, release_id: str) -> str:
    expires_at = int(datetime.now(UTC).timestamp()) + settings.release_download_url_expires_seconds
    return str(
        request.url_for("release_artifact", release_id=release_id).include_query_params(
            expires=expires_at,
            signature=_artifact_signature(release_id, expires_at),
        )
    )


def _download_url(
    request: Request,
    release: AppRelease,
    storage: CosObjectStorage,
) -> str:
    expires_seconds = settings.release_download_url_expires_seconds
    if settings.cos_custom_domain.strip():
        return storage.download_url(
            release.cos_object_key,
            expires_seconds=expires_seconds,
        )
    return _artifact_url(request, release.release_id)


@router.get("/latest", response_model=LatestReleaseResponse)
def latest_release(
    request: Request,
    repository: Annotated[PostgresReleaseRepository, Depends(get_release_repository)],
    platform: Literal["android"] = Query(default="android"),
    channel: Literal["internal"] = Query(default="internal"),
    version_code: int = Query(gt=0),
) -> LatestReleaseResponse:
    _consume_rate_limit(request, "latest")
    release = repository.find_latest(platform, channel)
    if release is None or release.version_code <= version_code:
        return LatestReleaseResponse(update_available=False)
    return LatestReleaseResponse(
        update_available=True,
        release=_response(release, version_code),
    )


@router.get("/bootstrap/android", response_class=RedirectResponse)
def bootstrap_android_release(
    request: Request,
    repository: Annotated[PostgresReleaseRepository, Depends(get_release_repository)],
    storage: Annotated[CosObjectStorage, Depends(get_cos_object_storage)],
    channel: Literal["internal"] = Query(default="internal"),
) -> RedirectResponse:
    _consume_rate_limit(request, "bootstrap")
    release = repository.find_latest("android", channel)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release is unavailable",
        )
    return RedirectResponse(
        _download_url(request, release, storage),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{release_id}/artifact", name="release_artifact")
def release_artifact(
    release_id: str,
    request: Request,
    repository: Annotated[PostgresReleaseRepository, Depends(get_release_repository)],
    storage: Annotated[CosObjectStorage, Depends(get_cos_object_storage)],
    expires: int = Query(gt=0),
    signature: str = Query(min_length=64, max_length=64),
) -> StreamingResponse:
    _consume_rate_limit(request, "artifact")
    now = int(datetime.now(UTC).timestamp())
    maximum_expiry = now + settings.release_download_url_expires_seconds + 60
    expected_signature = _artifact_signature(release_id, expires)
    if expires < now or expires > maximum_expiry or not hmac.compare_digest(
        signature,
        expected_signature,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Release download link is invalid or expired",
        )
    release = repository.get_active_by_id(release_id)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release is unavailable",
        )
    return StreamingResponse(
        storage.stream_bytes(release.cos_object_key),
        media_type="application/vnd.android.package-archive",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'attachment; filename="Echo.apk"',
            "Content-Length": str(release.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{release_id}/download", response_model=ReleaseDownloadResponse)
def release_download(
    release_id: str,
    body: ReleaseDownloadRequest,
    request: Request,
    repository: Annotated[PostgresReleaseRepository, Depends(get_release_repository)],
    storage: Annotated[CosObjectStorage, Depends(get_cos_object_storage)],
) -> ReleaseDownloadResponse:
    _consume_rate_limit(request, "download")
    release = repository.get_active(release_id, body.platform, body.channel)
    if release is None or release.version_code <= body.version_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release is unavailable",
        )
    expires_seconds = settings.release_download_url_expires_seconds
    return ReleaseDownloadResponse(
        release_id=release.release_id,
        download_url=_download_url(request, release, storage),
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
    )
