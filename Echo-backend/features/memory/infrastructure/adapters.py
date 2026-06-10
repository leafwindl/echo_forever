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
    """在边界处把仓储字典转换为纯领域对象。"""
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
    """基于 SQLite 仓储实现 MemoryRepository 协议。"""

    def list_memories(self, user_id: str, status: Optional[str], limit: int) -> List[Memory]:
        """按用户读取有限数量的记忆，避免跨用户访问。"""
        records = memory_repository.list_user_memories(user_id, status=status, limit=limit)
        return [_memory_from_record(record) for record in records]

    def list_active_memories(self, user_id: str, limit: int) -> List[Memory]:
        """只读取 active 记忆，因为只有有效事实应该影响后续上下文。"""
        return self.list_memories(user_id, status="active", limit=limit)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[Memory]:
        """按用户和记忆 ID 查询，在仓储层继续约束所有权。"""
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
        """在应用层校验通过后，持久化新的长期事实。"""
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
        """更新时重新置为 active，让用户的新表达覆盖旧状态。"""
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
        """模型识别为已有记忆时，只刷新元数据而不重复创建。"""
        return memory_repository.touch_user_memory(
            user_id=user_id,
            memory_id=memory_id,
            source_message_id=source_message_id,
        )

    def deactivate_memory(self, user_id: str, memory_id: str) -> bool:
        """用户纠正或撤销信息时，将记忆标记为 inactive。"""
        return memory_repository.deactivate_user_memory(user_id, memory_id)

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """面向用户删除操作时，对记忆做软删除。"""
        return memory_repository.delete_user_memory(user_id, memory_id)

    def clear_memories(self, user_id: str) -> int:
        """软删除单个用户的全部记忆，不影响聊天历史。"""
        return memory_repository.clear_user_memories(user_id)


class MemoryEmbeddingRepositoryAdapter(MemoryEmbeddingRepository):
    """记忆抽取流程使用的 Embedding 适配器；失败由应用层降级处理。"""

    async def upsert_memory_embedding(self, user_id: str, memory_id: str, content: str) -> bool:
        """Embedding 服务已配置时，创建或替换记忆向量。"""
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
        """源记忆不应再被召回时，删除对应向量。"""
        return vector_repository.delete_memory_embedding_record(user_id, memory_id)


class MemoryVectorIndexAdapter(MemoryVectorIndex):
    """记忆管理操作使用的向量索引适配器。"""

    def delete_memory_embedding(self, user_id: str, memory_id: str) -> bool:
        """通过 feature 边界移除单条向量。"""
        return vector_index.delete_memory_embedding(user_id, memory_id)

    def clear_memory_embeddings(self, user_id: str) -> int:
        """用户清空记忆后，移除该用户的全部向量。"""
        return vector_index.clear_memory_embeddings(user_id)

    async def backfill_user_memory_embeddings(self, user_id: str, limit: int) -> int:
        """复用正常抽取路径，为历史记忆补齐向量。"""
        return await vector_index.backfill_user_memory_embeddings(user_id, limit=limit)


class MemoryExtractionJobRepositoryAdapter(MemoryExtractionJobRepository):
    """持久化任务适配器，让记忆抽取能跨进程重启恢复。"""

    def create_extraction_job(self, payload: Dict[str, object]) -> str:
        """先持久化任务载荷，再尝试后台执行。"""
        return job_repository.create_job(MEMORY_EXTRACTION_JOB_TYPE, payload)

    def claim_job(self, job_id: str) -> bool:
        """认领任务可以避免多个 worker 重复处理同一个抽取任务。"""
        return job_repository.claim_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        """认领后再读取任务，确保执行使用的是持久化状态。"""
        return job_repository.get_job(job_id)

    def complete_job(self, job_id: str) -> bool:
        """标记成功，便于观测并避免重启后重复执行。"""
        return job_repository.complete_job(job_id)

    def fail_job(self, job_id: str, error: str) -> bool:
        """记录失败原因，避免重试状态和排错信息丢失。"""
        return job_repository.fail_job(job_id, error)

    def list_runnable_jobs(self, limit: int) -> List[Dict[str, object]]:
        """限制启动恢复数量，避免启动阶段被历史任务拖慢。"""
        return job_repository.list_runnable_jobs(MEMORY_EXTRACTION_JOB_TYPE, limit=limit)

    def reset_running_jobs(self) -> int:
        """恢复上一次进程异常退出时遗留的 running 任务。"""
        return job_repository.reset_running_jobs(MEMORY_EXTRACTION_JOB_TYPE)


class MemoryExtractionLLMAdapter(MemoryExtractionLLM):
    """用于结构化记忆抽取提示词的 LLM 适配器。"""

    async def request_memory_extraction(
        self,
        messages: list[dict],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """委托给已配置的 LLM Provider，不向应用层暴露供应商细节。"""
        llm_provider = get_llm_provider()
        return await llm_provider.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
