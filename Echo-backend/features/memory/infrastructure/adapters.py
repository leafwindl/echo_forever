from typing import Dict, List, Optional

from features.memory.domain.entities import MEMORY_EXTRACTION_JOB_TYPE, Memory, MemoryImportance
from features.memory.domain.repositories import (
    MemoryEmbeddingRepository,
    MemoryExtractionJobRepository,
    MemoryExtractionLLM,
    MemoryRepository,
    MemoryVectorIndex,
)
from providers.embedding_provider import get_embedding_provider
from providers.llm_provider import get_llm_provider
from repositories import job_repository
from repositories import memory_repository
from repositories import vector_repository
from features.memory.infrastructure import vector_index
from shared.config import settings


def _memory_from_record(record: Dict[str, object]) -> Memory:
    return Memory(
        memory_id=str(record["memory_id"]),
        user_id=str(record["user_id"]),
        memory_type=str(record["memory_type"]),
        content=str(record["content"]),
        source_message_id=record.get("source_message_id"),
        confidence=float(record.get("confidence") or 0),
        importance=MemoryImportance(int(record.get("importance") or 1)),
        status=str(record["status"]),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
        expires_at=record.get("expires_at"),
    )


class MemoryRepositoryAdapter(MemoryRepository):
    def list_memories(self, user_id: str, status: Optional[str], limit: int) -> List[Memory]:
        records = memory_repository.list_user_memories(user_id, status=status, limit=limit)
        return [_memory_from_record(record) for record in records]

    def list_active_memories(self, user_id: str, limit: int) -> List[Memory]:
        return self.list_memories(user_id, status="active", limit=limit)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[Memory]:
        record = memory_repository.get_user_memory(user_id, memory_id)
        return _memory_from_record(record) if record else None

    def add_memory(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        source_message_id: Optional[int],
        confidence: float,
        importance: int,
    ) -> str:
        return memory_repository.add_user_memory(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=importance,
        )

    def update_memory(
        self,
        user_id: str,
        memory_id: str,
        memory_type: str,
        content: str,
        source_message_id: Optional[int],
        confidence: float,
        importance: int,
    ) -> bool:
        return memory_repository.update_user_memory(
            user_id=user_id,
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=importance,
            status="active",
        )

    def touch_memory(
        self,
        user_id: str,
        memory_id: str,
        source_message_id: Optional[int],
    ) -> bool:
        return memory_repository.touch_user_memory(
            user_id=user_id,
            memory_id=memory_id,
            source_message_id=source_message_id,
        )

    def deactivate_memory(self, user_id: str, memory_id: str) -> bool:
        return memory_repository.deactivate_user_memory(user_id, memory_id)

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        return memory_repository.delete_user_memory(user_id, memory_id)

    def clear_memories(self, user_id: str) -> int:
        return memory_repository.clear_user_memories(user_id)


class MemoryEmbeddingRepositoryAdapter(MemoryEmbeddingRepository):
    async def upsert_memory_embedding(self, user_id: str, memory_id: str, content: str) -> bool:
        clean_content = content.strip()
        if not clean_content:
            return False

        embedding_provider = get_embedding_provider()
        embedding = await embedding_provider.create_embedding(clean_content, model=settings.embedding_model)
        vector_repository.upsert_memory_embedding_record(
            user_id=user_id,
            memory_id=memory_id,
            embedding_model=settings.embedding_model,
            embedding=embedding,
        )
        return True

    def delete_memory_embedding(self, user_id: str, memory_id: str) -> bool:
        return vector_repository.delete_memory_embedding_record(user_id, memory_id)


class MemoryVectorIndexAdapter(MemoryVectorIndex):
    def delete_memory_embedding(self, user_id: str, memory_id: str) -> bool:
        return vector_index.delete_memory_embedding(user_id, memory_id)

    def clear_memory_embeddings(self, user_id: str) -> int:
        return vector_index.clear_memory_embeddings(user_id)

    async def backfill_user_memory_embeddings(self, user_id: str, limit: int) -> int:
        return await vector_index.backfill_user_memory_embeddings(user_id, limit=limit)


class MemoryExtractionJobRepositoryAdapter(MemoryExtractionJobRepository):
    def create_extraction_job(self, payload: Dict[str, object]) -> str:
        return job_repository.create_job(MEMORY_EXTRACTION_JOB_TYPE, payload)

    def claim_job(self, job_id: str) -> bool:
        return job_repository.claim_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        return job_repository.get_job(job_id)

    def complete_job(self, job_id: str) -> bool:
        return job_repository.complete_job(job_id)

    def fail_job(self, job_id: str, error: str) -> bool:
        return job_repository.fail_job(job_id, error)

    def list_runnable_jobs(self, limit: int) -> List[Dict[str, object]]:
        return job_repository.list_runnable_jobs(MEMORY_EXTRACTION_JOB_TYPE, limit=limit)

    def reset_running_jobs(self) -> int:
        return job_repository.reset_running_jobs(MEMORY_EXTRACTION_JOB_TYPE)


class MemoryExtractionLLMAdapter(MemoryExtractionLLM):
    async def request_memory_extraction(
        self,
        messages: list[dict],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        llm_provider = get_llm_provider()
        return await llm_provider.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
