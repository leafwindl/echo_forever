import json
import logging
import math
from typing import Dict, Iterable, List, Optional

from config import settings
from services.embedding_client import create_embedding
from services.memory import _connect, get_user_memory, list_user_memories

logger = logging.getLogger(__name__)


def _encode_vector(vector: Iterable[float]) -> str:
    return json.dumps([float(value) for value in vector], separators=(",", ":"))


def _decode_vector(raw_vector: str) -> List[float]:
    values = json.loads(raw_vector)
    if not isinstance(values, list):
        return []
    return [float(value) for value in values]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _get_active_memory_map(user_id: str, limit: int = 200) -> Dict[str, Dict[str, object]]:
    memories = list_user_memories(user_id, status="active", limit=limit)
    return {str(memory["memory_id"]): memory for memory in memories}


def upsert_memory_embedding_record(
    user_id: str,
    memory_id: str,
    embedding_model: str,
    embedding: List[float],
):
    """写入或更新单条长期记忆 embedding。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_embeddings (memory_id, user_id, embedding_model, embedding, vector_store_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                user_id = excluded.user_id,
                embedding_model = excluded.embedding_model,
                embedding = excluded.embedding,
                vector_store_id = excluded.vector_store_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                memory_id,
                user_id,
                embedding_model,
                _encode_vector(embedding),
                memory_id,
            ),
        )
        conn.commit()


async def upsert_memory_embedding(
    user_id: str,
    memory_id: str,
    content: str,
) -> bool:
    """为单条长期记忆生成并保存 embedding。"""
    clean_content = content.strip()
    if not clean_content:
        return False

    embedding = await create_embedding(clean_content, model=settings.embedding_model)
    upsert_memory_embedding_record(
        user_id=user_id,
        memory_id=memory_id,
        embedding_model=settings.embedding_model,
        embedding=embedding,
    )
    logger.info("Memory embedding upserted for user_id=%s memory_id=%s", user_id, memory_id)
    return True


def delete_memory_embedding(user_id: str, memory_id: str) -> bool:
    """删除单条长期记忆向量，和用户主动删除记忆保持一致。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM memory_embeddings
            WHERE user_id = ? AND memory_id = ?
            """,
            (user_id, memory_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_memory_embeddings(user_id: str) -> int:
    """清空当前用户的长期记忆向量。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_embeddings WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount


def list_memory_embedding_records(user_id: str, embedding_model: Optional[str] = None) -> List[Dict[str, object]]:
    """读取当前用户 embedding 记录；只由向量适配层内部使用。"""
    query = """
        SELECT memory_id, embedding_model, embedding
        FROM memory_embeddings
        WHERE user_id = ? AND embedding IS NOT NULL
    """
    params: list[object] = [user_id]

    if embedding_model:
        query += " AND embedding_model = ?"
        params.append(embedding_model)

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    records = []
    for row in rows:
        try:
            vector = _decode_vector(row[2])
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Invalid embedding vector skipped for memory_id=%s", row[0])
            continue

        records.append({
            "memory_id": row[0],
            "embedding_model": row[1],
            "embedding": vector,
        })
    return records


async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, object]]:
    """按当前用户消息召回相关长期记忆。"""
    clean_query = query.strip()
    if not clean_query:
        return []

    memory_map = _get_active_memory_map(user_id)
    if not memory_map:
        return []

    query_embedding = await create_embedding(clean_query, model=settings.embedding_model)
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
    """为已有 active 记忆补齐 embedding，方便从旧阶段数据平滑升级。"""
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
    """调试辅助：读取已向量化的记忆原文。"""
    return get_user_memory(user_id, memory_id)
