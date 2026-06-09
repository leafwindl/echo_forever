import json
import logging
import sqlite3
from typing import Dict, Iterable, List, Optional

from db.connection import get_connection, transaction

logger = logging.getLogger(__name__)


def _encode_vector(vector: Iterable[float]) -> str:
    return json.dumps([float(value) for value in vector], separators=(",", ":"))


def _decode_vector(raw_vector: str) -> List[float]:
    values = json.loads(raw_vector)
    if not isinstance(values, list):
        return []
    return [float(value) for value in values]


def upsert_memory_embedding_record(
    user_id: str,
    memory_id: str,
    embedding_model: str,
    embedding: List[float],
    conn: Optional[sqlite3.Connection] = None,
):
    if conn is None:
        with transaction() as tx:
            return upsert_memory_embedding_record(user_id, memory_id, embedding_model, embedding, conn=tx)

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


def delete_memory_embedding_record(user_id: str, memory_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    if conn is None:
        with transaction() as tx:
            return delete_memory_embedding_record(user_id, memory_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM memory_embeddings
        WHERE user_id = ? AND memory_id = ?
        """,
        (user_id, memory_id),
    )
    return cursor.rowcount > 0


def clear_memory_embedding_records(user_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    if conn is None:
        with transaction() as tx:
            return clear_memory_embedding_records(user_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM memory_embeddings WHERE user_id = ?", (user_id,))
    return cursor.rowcount


def list_memory_embedding_records(user_id: str, embedding_model: Optional[str] = None) -> List[Dict[str, object]]:
    query = """
        SELECT memory_id, embedding_model, embedding
        FROM memory_embeddings
        WHERE user_id = ? AND embedding IS NOT NULL
    """
    params: list[object] = [user_id]

    if embedding_model:
        query += " AND embedding_model = ?"
        params.append(embedding_model)

    with get_connection() as conn:
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
