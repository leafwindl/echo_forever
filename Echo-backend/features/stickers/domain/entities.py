from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Sticker:
    sticker_id: str
    owner_type: str
    source: str
    url: str
    content_type: str
    description: str
    semantic_tags: tuple[str, ...]
    status: str
    created_at: datetime
    priority: int = 100
    similarity_score: float | None = None

