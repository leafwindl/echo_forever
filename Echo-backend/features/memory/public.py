from features.memory.application.memory_extraction import MemoryExtractionService
from features.memory.application.memory_management import MemoryManagementService
from features.memory.domain.entities import (
    MEMORY_EXTRACTION_JOB_TYPE,
    InvalidMemoryStatusError,
    Memory,
    MemoryBackfillResult,
    MemoryClearResult,
    MemoryDeleteResult,
    MemoryExtractionResult,
    MemoryGateResult,
    MemoryListResult,
    MemoryNotFoundError,
    MemoryOperationError,
    MemoryValidationError,
)
from features.memory.domain.extraction_rules import parse_memory_extraction, should_extract_memory
from features.memory.infrastructure.container import (
    get_memory_extraction_service,
    get_memory_management_service,
)
from features.memory.infrastructure.vector_index import (
    list_memory_embedding_records,
    retrieve_relevant_memories,
)


def list_memories(user_id: str, memory_status: str = "active", limit: int = 50) -> MemoryListResult:
    service = get_memory_management_service()
    return service.list_memories(user_id=user_id, memory_status=memory_status, limit=limit)


def delete_memory(user_id: str, memory_id: str) -> MemoryDeleteResult:
    service = get_memory_management_service()
    return service.delete_memory(user_id=user_id, memory_id=memory_id)


def clear_memories(user_id: str) -> MemoryClearResult:
    service = get_memory_management_service()
    return service.clear_memories(user_id=user_id)


async def backfill_memory_embeddings(user_id: str, limit: int = 100) -> MemoryBackfillResult:
    service = get_memory_management_service()
    return await service.backfill_memory_embeddings(user_id=user_id, limit=limit)


def schedule_memory_extraction(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: int | None = None,
) -> MemoryGateResult:
    service = get_memory_extraction_service()
    return service.schedule_memory_extraction(
        user_id=user_id,
        user_message=user_message,
        assistant_reply=assistant_reply,
        source_message_id=source_message_id,
    )


def resume_pending_memory_extraction_jobs(limit: int = 20) -> int:
    service = get_memory_extraction_service()
    return service.resume_pending_memory_extraction_jobs(limit=limit)

__all__ = [
    "MEMORY_EXTRACTION_JOB_TYPE",
    "InvalidMemoryStatusError",
    "Memory",
    "MemoryBackfillResult",
    "MemoryClearResult",
    "MemoryDeleteResult",
    "MemoryExtractionResult",
    "MemoryExtractionService",
    "MemoryGateResult",
    "MemoryListResult",
    "MemoryManagementService",
    "MemoryNotFoundError",
    "MemoryOperationError",
    "MemoryValidationError",
    "backfill_memory_embeddings",
    "clear_memories",
    "delete_memory",
    "list_memories",
    "list_memory_embedding_records",
    "parse_memory_extraction",
    "retrieve_relevant_memories",
    "resume_pending_memory_extraction_jobs",
    "schedule_memory_extraction",
    "should_extract_memory",
]
