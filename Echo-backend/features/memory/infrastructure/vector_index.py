import logging
import math
from typing import Dict, List, Optional

from providers.embedding_provider import get_embedding_provider
from repositories.memory_repository import get_user_memory, list_user_memories
from repositories.vector_repository import (
    clear_memory_embedding_records,
    delete_memory_embedding_record,
    list_memory_embedding_records as list_memory_embedding_records_from_repo,
    upsert_memory_embedding_record as upsert_memory_embedding_record_in_repo,
)
from shared.config import settings

logger = logging.getLogger(__name__)


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    """向量不兼容时返回 0，让召回逻辑可以安全降级。"""
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _get_active_memory_map(user_id: str, limit: int = 200) -> Dict[str, Dict[str, object]]:
    """只读取有限数量的 active 记忆，因为向量记录必须回指现存记忆才有意义。"""
    memories = list_user_memories(user_id, status="active", limit=limit)
    return {str(memory["memory_id"]): memory for memory in memories}


def upsert_memory_embedding_record(
    user_id: str,
    memory_id: str,
    embedding_model: str,
    embedding: List[float],
):
    """保留这一层包装，让 feature 通过自己的边界访问共享仓储。"""
    upsert_memory_embedding_record_in_repo(user_id, memory_id, embedding_model, embedding)


async def upsert_memory_embedding(
    user_id: str,
    memory_id: str,
    content: str,
) -> bool:
    """仅在 embedding 已配置且内容有效时创建向量。"""
    clean_content = content.strip()
    if not clean_content:
        return False

    embedding_provider = get_embedding_provider()
    embedding = await embedding_provider.create_embedding(clean_content, model=settings.embedding_model)
    upsert_memory_embedding_record(
        user_id=user_id,
        memory_id=memory_id,
        embedding_model=settings.embedding_model,
        embedding=embedding,
    )
    logger.info("Memory embedding upserted for user_id=%s memory_id=%s", user_id, memory_id)
    return True


def delete_memory_embedding(user_id: str, memory_id: str) -> bool:
    """记忆删除时移除向量，避免检索重新召回旧事实。"""
    return delete_memory_embedding_record(user_id, memory_id)


def clear_memory_embeddings(user_id: str) -> int:
    """用户清空记忆时批量移除向量。"""
    return clear_memory_embedding_records(user_id)


def list_memory_embedding_records(
    user_id: str,
    embedding_model: Optional[str] = None,
) -> List[Dict[str, object]]:
    """向上下文构建暴露向量记录，同时隐藏底层仓储细节。"""
    return list_memory_embedding_records_from_repo(user_id, embedding_model=embedding_model)


async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, object]]:
    """Embedding 可用时，根据语义相似度召回相关记忆。"""
    clean_query = query.strip()
    if not clean_query:
        return []

    memory_map = _get_active_memory_map(user_id)
    if not memory_map:
        return []

    embedding_provider = get_embedding_provider()
    query_embedding = await embedding_provider.create_embedding(clean_query, model=settings.embedding_model)
    records = list_memory_embedding_records(user_id, embedding_model=settings.embedding_model)
    scored_memories: List[Dict[str, object]] = []
    min_score = settings.memory_vector_score_threshold if score_threshold is None else score_threshold

    for record in records:
        memory_id = str(record["memory_id"])
        memory = memory_map.get(memory_id)
        if not memory:
            continue

        score = _cosine_similarity(query_embedding, record["embedding"])
        if score < min_score:
            continue

        scored_memory = dict(memory)
        scored_memory["similarity_score"] = score
        scored_memories.append(scored_memory)

    scored_memories.sort(
        key=lambda memory: (
            float(memory.get("similarity_score", 0)),
            int(memory.get("importance", 0)),
        ),
        reverse=True,
    )
    return scored_memories[: top_k or settings.memory_vector_top_k]


async def backfill_user_memory_embeddings(user_id: str, limit: int = 50) -> int:
    """Embedding 服务配置后，让旧记忆也能参与向量召回。"""
    memories = list_user_memories(user_id, status="active", limit=limit)
    existing_ids = {
        str(record["memory_id"])
        for record in list_memory_embedding_records(user_id, embedding_model=settings.embedding_model)
    }

    count = 0
    for memory in memories:
        memory_id = str(memory["memory_id"])
        if memory_id in existing_ids:
            continue
        if await upsert_memory_embedding(user_id, memory_id, str(memory["content"])):
            count += 1
    return count


def get_embedding_memory(user_id: str, memory_id: str) -> Optional[Dict[str, object]]:
    """调试辅助：确认向量记录对应的原始记忆。"""
    return get_user_memory(user_id, memory_id)
