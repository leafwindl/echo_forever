import logging
from typing import Optional

from features.memory.domain.entities import (
    VALID_MEMORY_STATUSES,
    InvalidMemoryStatusError,
    MemoryBackfillResult,
    MemoryClearResult,
    MemoryDeleteResult,
    MemoryListResult,
    MemoryNotFoundError,
    MemoryOperationError,
    MemoryValidationError,
)
from features.memory.domain.repositories import MemoryRepository, MemoryVectorIndex

logger = logging.getLogger(__name__)


def normalize_memory_status(memory_status: str) -> Optional[str]:
    clean_status = memory_status.strip().lower()
    if clean_status == "all":
        return None
    if clean_status in VALID_MEMORY_STATUSES:
        return clean_status
    raise InvalidMemoryStatusError("Invalid memory status")


def clamp_limit(limit: int, maximum: int) -> int:
    return max(1, min(limit, maximum))


class MemoryManagementService:
    def __init__(
        self,
        memory_repository: MemoryRepository,
        vector_index: MemoryVectorIndex,
    ):
        self.memory_repository = memory_repository
        self.vector_index = vector_index

    def list_memories(self, user_id: str, memory_status: str = "active", limit: int = 50) -> MemoryListResult:
        normalized_status = normalize_memory_status(memory_status)
        safe_limit = clamp_limit(limit, 200)
        memories = self.memory_repository.list_memories(
            user_id=user_id,
            status=normalized_status,
            limit=safe_limit,
        )
        return MemoryListResult(memories=memories, count=len(memories))

    def delete_memory(self, user_id: str, memory_id: str) -> MemoryDeleteResult:
        clean_memory_id = memory_id.strip()
        if not clean_memory_id:
            raise MemoryValidationError("Missing memory_id")

        existing_memory = self.memory_repository.get_memory(user_id, clean_memory_id)
        if not existing_memory:
            raise MemoryNotFoundError("Memory not found")

        if not self.memory_repository.delete_memory(user_id, clean_memory_id):
            raise MemoryOperationError("Failed to delete memory")

        try:
            self.vector_index.delete_memory_embedding(user_id, clean_memory_id)
        except Exception:
            logger.exception("Failed to delete memory embedding for memory_id=%s", clean_memory_id)

        return MemoryDeleteResult(memory_id=clean_memory_id, status="deleted")

    def clear_memories(self, user_id: str) -> MemoryClearResult:
        cleared_count = self.memory_repository.clear_memories(user_id)
        try:
            self.vector_index.clear_memory_embeddings(user_id)
        except Exception:
            logger.exception("Failed to clear memory embeddings for user_id=%s", user_id)
        return MemoryClearResult(cleared_count=cleared_count)

    async def backfill_memory_embeddings(self, user_id: str, limit: int = 100) -> MemoryBackfillResult:
        safe_limit = clamp_limit(limit, 500)
        backfilled_count = await self.vector_index.backfill_user_memory_embeddings(
            user_id=user_id,
            limit=safe_limit,
        )
        return MemoryBackfillResult(backfilled_count=backfilled_count)
