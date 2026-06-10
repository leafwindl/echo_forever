from typing import Dict, List, Optional, Protocol

from features.memory.domain.entities import Memory


class MemoryRepository(Protocol):
    """长期记忆的持久化契约。"""

    def list_memories(self, user_id: str, status: Optional[str], limit: int) -> List[Memory]:
        ...

    def list_active_memories(self, user_id: str, limit: int) -> List[Memory]:
        ...

    def get_memory(self, user_id: str, memory_id: str) -> Optional[Memory]:
        ...

    def add_memory(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        source_message_id: Optional[int],
        confidence: float,
        importance: int,
    ) -> str:
        ...

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
        ...

    def touch_memory(
        self,
        user_id: str,
        memory_id: str,
        source_message_id: Optional[int],
    ) -> bool:
        ...

    def deactivate_memory(self, user_id: str, memory_id: str) -> bool:
        ...

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        ...

    def clear_memories(self, user_id: str) -> int:
        ...


class MemoryEmbeddingRepository(Protocol):
    """保持记忆向量与记忆记录一致的契约。"""

    async def upsert_memory_embedding(self, user_id: str, memory_id: str, content: str) -> bool:
        ...

    def delete_memory_embedding(self, user_id: str, memory_id: str) -> bool:
        ...


class MemoryVectorIndex(Protocol):
    """向量索引管理操作的契约。"""

    def delete_memory_embedding(self, user_id: str, memory_id: str) -> bool:
        ...

    def clear_memory_embeddings(self, user_id: str) -> int:
        ...

    async def backfill_user_memory_embeddings(self, user_id: str, limit: int) -> int:
        ...


class MemoryExtractionJobRepository(Protocol):
    """记忆抽取后台任务的持久化契约。"""

    def create_extraction_job(self, payload: Dict[str, object]) -> str:
        ...

    def claim_job(self, job_id: str) -> bool:
        ...

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        ...

    def complete_job(self, job_id: str) -> bool:
        ...

    def fail_job(self, job_id: str, error: str) -> bool:
        ...

    def list_runnable_jobs(self, limit: int) -> List[Dict[str, object]]:
        ...

    def reset_running_jobs(self) -> int:
        ...


class MemoryExtractionLLM(Protocol):
    """请求 LLM 返回结构化记忆操作的 Provider 契约。"""

    async def request_memory_extraction(
        self,
        messages: list[dict],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        ...
