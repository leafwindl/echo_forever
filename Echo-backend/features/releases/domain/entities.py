from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AppRelease:
    release_id: str
    platform: str
    channel: str
    package_name: str
    version_name: str
    version_code: int
    minimum_version_code: int
    cos_object_key: str
    sha256: str
    size_bytes: int
    release_notes: tuple[str, ...]
    mandatory: bool
    status: str
    published_at: datetime | None

    def is_mandatory_for(self, current_version_code: int) -> bool:
        return self.mandatory or current_version_code < self.minimum_version_code
