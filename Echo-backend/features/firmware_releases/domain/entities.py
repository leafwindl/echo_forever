from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FirmwareRelease:
    release_id: str
    board_type: str
    board_variant: str
    version: str
    cos_object_key: str
    sha256: str
    size_bytes: int
    release_notes: tuple[str, ...]
    status: str
    published_at: datetime | None
