from typing import Optional

from pydantic import BaseModel


class MemoryItem(BaseModel):
    memory_id: str
    memory_type: str
    content: str
    source_message_id: Optional[int] = None
    confidence: float
    importance: int
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryItem]
    count: int


class MemoryClearRequest(BaseModel):
    user_id: str


class MemoryDeleteResponse(BaseModel):
    memory_id: str
    status: str


class MemoryClearResponse(BaseModel):
    cleared_count: int


class MemoryBackfillEmbeddingsRequest(BaseModel):
    user_id: str
    limit: int = 100


class MemoryBackfillEmbeddingsResponse(BaseModel):
    backfilled_count: int
