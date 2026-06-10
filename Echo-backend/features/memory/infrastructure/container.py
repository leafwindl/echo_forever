from typing import Optional

from features.memory.application.memory_management import MemoryManagementService
from features.memory.application.memory_extraction import MemoryExtractionService
from features.memory.domain.entities import MemoryExtractionConfig
from features.memory.infrastructure.adapters import (
    MemoryEmbeddingRepositoryAdapter,
    MemoryExtractionJobRepositoryAdapter,
    MemoryExtractionLLMAdapter,
    MemoryRepositoryAdapter,
    MemoryVectorIndexAdapter,
)
from shared.config import settings

_memory_extraction_service: Optional[MemoryExtractionService] = None
_memory_management_service: Optional[MemoryManagementService] = None


def get_memory_extraction_service() -> MemoryExtractionService:
    """集中装配具体适配器，让应用层始终通过构造函数接收依赖。"""
    global _memory_extraction_service
    if _memory_extraction_service is None:
        _memory_extraction_service = MemoryExtractionService(
            memory_repository=MemoryRepositoryAdapter(),
            embedding_repository=MemoryEmbeddingRepositoryAdapter(),
            job_repository=MemoryExtractionJobRepositoryAdapter(),
            llm=MemoryExtractionLLMAdapter(),
            config=MemoryExtractionConfig(
                model=settings.memory_extraction_model,
                temperature=settings.memory_extraction_temperature,
                max_tokens=settings.memory_extraction_max_tokens,
            ),
        )
    return _memory_extraction_service


def get_memory_management_service() -> MemoryManagementService:
    """为记忆管理用例装配当前存储和向量适配器。"""
    global _memory_management_service
    if _memory_management_service is None:
        _memory_management_service = MemoryManagementService(
            memory_repository=MemoryRepositoryAdapter(),
            vector_index=MemoryVectorIndexAdapter(),
        )
    return _memory_management_service


def reset_memory_extraction_service_for_tests():
    """测试时重置单例，确保每个用例能获得干净依赖。"""
    global _memory_extraction_service, _memory_management_service
    _memory_extraction_service = None
    _memory_management_service = None
