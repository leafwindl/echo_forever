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
    MemoryRecallHit,
    MemoryValidationError,
)
from features.memory.domain.extraction_rules import parse_memory_extraction, should_extract_memory
from features.memory.infrastructure.container import (
    get_memory_extraction_service,
    get_memory_management_service,
)
from features.memory.infrastructure.postgres_repositories import add_user_memory
from features.memory.infrastructure.vector_index import (
    list_memory_embedding_records,
    retrieve_relevant_memories,
    upsert_memory_embedding,
)


def list_memories(user_id: str, memory_status: str = "active", limit: int = 50) -> MemoryListResult:
    """稳定的模块入口：供界面或管理能力读取记忆，不暴露应用层细节。"""
    service = get_memory_management_service()
    return service.list_memories(user_id=user_id, memory_status=memory_status, limit=limit)


async def remember_presence_thought(
    user_id: str,
    *,
    content: str,
    salience: float,
    source_message_id: int | None = None,
) -> str | None:
    """Persist a high-salience inner thought as a long-term reflection."""
    cleaned = " ".join(content.split())
    if len(cleaned) < 8:
        return None
    existing = list_memories(user_id, limit=50).memories
    normalized = cleaned[:120]
    if any(normalized == " ".join(item.content.split())[:120] for item in existing):
        return None
    importance = 5 if salience >= 0.85 else 4
    memory_id = add_user_memory(
        user_id,
        "reflection",
        cleaned[:500],
        source_message_id=source_message_id,
        confidence=min(0.95, 0.65 + salience * 0.3),
        importance=importance,
    )
    await upsert_memory_embedding(user_id, memory_id, cleaned)
    return memory_id


async def recall_memory(user_id: str, query: str, limit: int = 1) -> list[MemoryRecallHit]:
    """Stable one-cue recall for companion workers; falls back to importance."""
    cleaned = query.strip()
    if cleaned:
        try:
            rows = await retrieve_relevant_memories(user_id, cleaned, top_k=limit)
        except Exception:
            rows = []
        if rows:
            return [
                MemoryRecallHit(
                    memory_id=str(row["memory_id"]),
                    content=str(row["content"]),
                    importance=int(row.get("importance") or 3),
                    similarity=float(row.get("similarity_score") or 0.0),
                )
                for row in rows
            ]
    memories = list_memories(user_id, limit=max(limit, 5)).memories
    memories.sort(key=lambda item: item.importance.value, reverse=True)
    return [
        MemoryRecallHit(
            memory_id=item.memory_id,
            content=item.content,
            importance=item.importance.value,
        )
        for item in memories[:limit]
    ]


def delete_memory(user_id: str, memory_id: str) -> MemoryDeleteResult:
    """稳定的模块入口：删除用户自己的长期记忆。"""
    service = get_memory_management_service()
    return service.delete_memory(user_id=user_id, memory_id=memory_id)


def clear_memories(user_id: str) -> MemoryClearResult:
    """稳定的模块入口：清空长期记忆，但保留聊天历史。"""
    service = get_memory_management_service()
    return service.clear_memories(user_id=user_id)


def cancel_pending_memory_extraction_jobs(user_id: str) -> int:
    """取消该用户尚未完成的记忆抽取任务，避免重置后旧任务回写。"""
    from features.memory.infrastructure.postgres_repositories import (
        cancel_user_extraction_jobs,
    )

    return cancel_user_extraction_jobs(user_id)


async def backfill_memory_embeddings(user_id: str, limit: int = 100) -> MemoryBackfillResult:
    """稳定的模块入口：让已有记忆补齐向量并参与检索。"""
    service = get_memory_management_service()
    return await service.backfill_memory_embeddings(user_id=user_id, limit=limit)


def schedule_memory_extraction(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: int | None = None,
    candidate_user_messages: tuple[tuple[int, str], ...] = (),
    force_batch_review: bool = False,
) -> MemoryGateResult:
    """稳定的模块入口：供 Chat 在一轮对话完成后调度记忆抽取。"""
    service = get_memory_extraction_service()
    return service.schedule_memory_extraction(
        user_id=user_id,
        user_message=user_message,
        assistant_reply=assistant_reply,
        source_message_id=source_message_id,
        candidate_user_messages=candidate_user_messages,
        force_batch_review=force_batch_review,
    )


def resume_pending_memory_extraction_jobs(limit: int = 20) -> int:
    """稳定的模块入口：供应用启动时恢复持久化后台任务。"""
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
    "MemoryRecallHit",
    "MemoryValidationError",
    "backfill_memory_embeddings",
    "cancel_pending_memory_extraction_jobs",
    "clear_memories",
    "delete_memory",
    "list_memories",
    "list_memory_embedding_records",
    "parse_memory_extraction",
    "recall_memory",
    "remember_presence_thought",
    "retrieve_relevant_memories",
    "resume_pending_memory_extraction_jobs",
    "schedule_memory_extraction",
    "should_extract_memory",
]
