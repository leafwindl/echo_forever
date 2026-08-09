from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass(frozen=True)
class DailyLetter:
    letter_id: str
    local_date: date
    timezone: str
    status: str
    subject: str
    content: str
    published_at: datetime | None
    read_at: datetime | None
    image_url: str = ""
    image_width: int | None = None
    image_height: int | None = None


@dataclass(frozen=True)
class LetterGenerationTask:
    letter_id: str
    user_id: str
    local_date: date
    timezone: str
    scheduled_at: datetime
    publish_at: datetime
    attempt_count: int
    max_attempts: int
    source_messages: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LetterAgentOutput:
    subject: str
    content: str
    mood: str
    core_topics: tuple[str, ...]
    reflection: str
    closing_style: str
    image_brief: dict[str, Any]
    source_message_ids: tuple[int, ...]
    source_memory_ids: tuple[str, ...]


@dataclass(frozen=True)
class LetterPreference:
    enabled: bool
    timezone: str
    publish_time: time

