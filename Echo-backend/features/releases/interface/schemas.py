from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReleaseResponse(BaseModel):
    release_id: str
    platform: Literal["android"]
    channel: Literal["internal"]
    package_name: str
    version_name: str
    version_code: int = Field(gt=0)
    minimum_version_code: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    release_notes: list[str] = Field(default_factory=list)
    mandatory: bool
    published_at: datetime | None = None


class LatestReleaseResponse(BaseModel):
    update_available: bool
    release: ReleaseResponse | None = None


class ReleaseDownloadRequest(BaseModel):
    platform: Literal["android"] = "android"
    channel: Literal["internal"] = "internal"
    version_code: int = Field(gt=0)


class ReleaseDownloadResponse(BaseModel):
    release_id: str
    download_url: str
    expires_at: datetime
