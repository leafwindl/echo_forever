from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
        download_url=storage.download_url(
            release.cos_object_key,
            expires_seconds=expires_seconds,
        ),
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
    )
