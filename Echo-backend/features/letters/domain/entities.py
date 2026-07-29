from dataclasses import dataclass
from datetime import date, datetime, time


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


@dataclass(frozen=True)
class LetterPreference:
    enabled: bool
    timezone: str
    publish_time: time

