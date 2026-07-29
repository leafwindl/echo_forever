from datetime import datetime

from pydantic import BaseModel, Field


class StickerResponse(BaseModel):
    sticker_id: str
    owner_type: str
    source: str
    url: str
    content_type: str
    description: str
    semantic_tags: list[str]
    status: str
    created_at: datetime


class StickerListResponse(BaseModel):
    items: list[StickerResponse] = Field(default_factory=list)


class StickerGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    intent: str = Field(default="", max_length=100)


class StickerGenerationResponse(BaseModel):
    job_id: str
    status: str
    generated_sticker_id: str | None = None
    error_code: str | None = None

