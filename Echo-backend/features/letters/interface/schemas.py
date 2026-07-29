from datetime import date, datetime

from pydantic import BaseModel, Field


class LetterResponse(BaseModel):
    letter_id: str
    local_date: date
    timezone: str
    status: str
    subject: str
    content: str
    published_at: datetime | None = None
    read_at: datetime | None = None


class LetterListResponse(BaseModel):
    items: list[LetterResponse] = Field(default_factory=list)
    unread_count: int = 0


class LetterPreferenceRequest(BaseModel):
    enabled: bool = True
    timezone: str = Field(min_length=1, max_length=80)
    publish_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class LetterPreferenceResponse(LetterPreferenceRequest):
    pass

