import json
import logging
import uuid
from typing import Dict, Iterable, List, Optional

from db.postgres_connection import get_connection, transaction
from features.auth.public import ensure_user_identity

logger = logging.getLogger(__name__)

MEMORY_JOB_RUNNABLE_STATUSES = ("pending", "retry")


def _row_to_memory(row) -> Dict[str, object]:
    return {
        "memory_id": row["memory_id"],
        "user_id": row["user_id"],
        "memory_type": row["memory_type"],
        "content": row["content"],
        "source_message_id": row["source_message_id"],
        "confidence": float(row["confidence"] or 0),
        "importance": int(row["importance"] or 0),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
    }


def list_user_memories(
    user_id: str,
    status: Optional[str] = "active",
    limit: int = 20,
) -> List[Dict[str, object]]:
    query = """
        SELECT
            memory_id, user_id, memory_type, content, source_message_id,
            confidence, importance, status, created_at, updated_at, expires_at
        FROM user_memories
        WHERE user_id = %s
    """
    params: list[object] = [user_id]

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY importance DESC, updated_at DESC, id DESC"
    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [_row_to_memory(row) for row in rows]


def get_user_memory(user_id: str, memory_id: str) -> Optional[Dict[str, object]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    memory_id, user_id, memory_type, content, source_message_id,
                    confidence, importance, status, created_at, updated_at, expires_at
                FROM user_memories
                WHERE user_id = %s AND memory_id = %s
                """,
                (user_id, memory_id),
            )
            row = cursor.fetchone()

    return _row_to_memory(row) if row else None


def add_user_memory(
    user_id: str,
    memory_type: str,
    content: str,
    source_message_id: Optional[int] = None,
    confidence: float = 0.8,
    importance: int = 3,
    conn=None,
) -> str:
    if conn is None:
        with transaction() as tx:
            return add_user_memory(
                user_id,
                memory_type,
                content,
                source_message_id,
                confidence,
                importance,
                conn=tx,
            )

    clean_content = content.strip()
    if not clean_content:
        raise ValueError("Memory content cannot be empty")

    ensure_user_identity(user_id=user_id, conn=conn)
    memory_id = f"mem_{uuid.uuid4().hex}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_memories (
                memory_id, user_id, memory_type, content,
                source_message_id, confidence, importance
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (memory_id, user_id, memory_type, clean_content, source_message_id, confidence, importance),
        )
    return memory_id


def update_user_memory(
    user_id: str,
    memory_id: str,
    memory_type: Optional[str] = None,
    content: Optional[str] = None,
    source_message_id: Optional[int] = None,
    confidence: Optional[float] = None,
    importance: Optional[int] = None,
    status: Optional[str] = None,
    conn=None,
) -> bool:
    if conn is None:
        with transaction() as tx:
            return update_user_memory(
                user_id,
                memory_id,
                memory_type,
                content,
                source_message_id,
                confidence,
                importance,
                status,
                conn=tx,
            )

    assignments = ["updated_at = NOW()"]
    params: list[object] = []

    if memory_type is not None:
        assignments.append("memory_type = %s")
        params.append(memory_type)
    if content is not None:
        clean_content = content.strip()
        if not clean_content:
            return False
        assignments.append("content = %s")
        params.append(clean_content)
    if source_message_id is not None:
        assignments.append("source_message_id = %s")
        params.append(source_message_id)
    if confidence is not None:
        assignments.append("confidence = %s")
        params.append(confidence)
    if importance is not None:
        assignments.append("importance = %s")
        params.append(importance)
    if status is not None:
        assignments.append("status = %s")
        params.append(status)

    params.extend([user_id, memory_id])
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE user_memories
            SET {", ".join(assignments)}
            WHERE user_id = %s AND memory_id = %s
            """,
            params,
        )
        return cursor.rowcount > 0


def touch_user_memory(
    user_id: str,
    memory_id: str,
    source_message_id: Optional[int] = None,
) -> bool:
    return update_user_memory(
        user_id=user_id,
        memory_id=memory_id,
        source_message_id=source_message_id,
    )


def deactivate_user_memory(user_id: str, memory_id: str) -> bool:
    return update_user_memory(user_id=user_id, memory_id=memory_id, status="inactive")


def delete_user_memory(user_id: str, memory_id: str) -> bool:
    return update_user_memory(user_id=user_id, memory_id=memory_id, status="deleted")


def clear_user_memories(user_id: str, conn=None) -> int:
    if conn is None:
        with transaction() as tx:
            return clear_user_memories(user_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE user_memories
            SET status = 'deleted',
                updated_at = NOW()
            WHERE user_id = %s AND (status IS NULL OR status != 'deleted')
            """,
            (user_id,),
        )
        return cursor.rowcount


def _vector_literal(vector: Iterable[float]) -> str:
    values = [float(value) for value in vector]
    return "[" + ",".join(str(value) for value in values) + "]"


def _decode_vector(raw_vector) -> List[float]:
    if raw_vector is None:
        return []
    if isinstance(raw_vector, list):
        return [float(value) for value in raw_vector]
    vector_text = str(raw_vector).strip()
    if not vector_text:
        return []
    if vector_text.startswith("[") and vector_text.endswith("]"):
        vector_text = vector_text[1:-1]
    return [float(value) for value in vector_text.split(",") if value.strip()]


def upsert_memory_embedding_record(
    user_id: str,
    memory_id: str,
    embedding_model: str,
    embedding: List[float],
    conn=None,
) -> None:
    if conn is None:
        with transaction() as tx:
            return upsert_memory_embedding_record(user_id, memory_id, embedding_model, embedding, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO memory_embeddings (memory_id, user_id, embedding_model, embedding, vector_store_id)
            VALUES (%s, %s, %s, %s::vector, %s)
            ON CONFLICT(memory_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                embedding_model = EXCLUDED.embedding_model,
                embedding = EXCLUDED.embedding,
                vector_store_id = EXCLUDED.vector_store_id,
                updated_at = NOW()
            """,
            (
                memory_id,
                user_id,
                embedding_model,
                _vector_literal(embedding),
                memory_id,
            ),
        )


def delete_memory_embedding_record(user_id: str, memory_id: str, conn=None) -> bool:
    if conn is None:
        with transaction() as tx:
            return delete_memory_embedding_record(user_id, memory_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM memory_embeddings
            WHERE user_id = %s AND memory_id = %s
            """,
            (user_id, memory_id),
        )
        return cursor.rowcount > 0


def clear_memory_embedding_records(user_id: str, conn=None) -> int:
    if conn is None:
        with transaction() as tx:
            return clear_memory_embedding_records(user_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM memory_embeddings WHERE user_id = %s", (user_id,))
        return cursor.rowcount


def list_memory_embedding_records(user_id: str, embedding_model: Optional[str] = None) -> List[Dict[str, object]]:
    query = """
        SELECT memory_id, embedding_model, embedding::text AS embedding
        FROM memory_embeddings
        WHERE user_id = %s
    """
    params: list[object] = [user_id]

    if embedding_model:
        query += " AND embedding_model = %s"
        params.append(embedding_model)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    records = []
    for row in rows:
        try:
            vector = _decode_vector(row["embedding"])
        except (TypeError, ValueError):
            logger.warning("Invalid embedding vector skipped for memory_id=%s", row["memory_id"])
            continue
        records.append({
            "memory_id": row["memory_id"],
            "embedding_model": row["embedding_model"],
            "embedding": vector,
        })
    return records


def _row_to_job(row) -> Dict[str, object]:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "job_id": row["job_id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "payload": payload,
        "attempts": int(row["attempts"] or 0),
        "max_attempts": int(row["max_attempts"] or 0),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def create_job(
    job_type: str,
    payload: Dict[str, object],
    max_attempts: int = 3,
    conn=None,
) -> str:
    if conn is None:
        with transaction() as tx:
            return create_job(job_type, payload, max_attempts=max_attempts, conn=tx)

    job_id = f"job_{uuid.uuid4().hex}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO background_jobs (job_id, job_type, payload, max_attempts)
            VALUES (%s, %s, %s::jsonb, %s)
            """,
            (job_id, job_type, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), max_attempts),
        )
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, object]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, job_type, status, payload, attempts, max_attempts,
                       error, created_at, updated_at, started_at, finished_at
                FROM background_jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()
    return _row_to_job(row) if row else None


def claim_job(job_id: str, conn=None) -> bool:
    if conn is None:
        with transaction() as tx:
            return claim_job(job_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = 'running',
                attempts = attempts + 1,
                error = NULL,
                started_at = NOW(),
                updated_at = NOW()
            WHERE job_id = %s
              AND status IN ('pending', 'retry')
              AND attempts < max_attempts
            """,
            (job_id,),
        )
        return cursor.rowcount > 0


def complete_job(job_id: str, conn=None) -> bool:
    if conn is None:
        with transaction() as tx:
            return complete_job(job_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = 'completed',
                finished_at = NOW(),
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (job_id,),
        )
        return cursor.rowcount > 0


def fail_job(job_id: str, error: str, conn=None) -> bool:
    if conn is None:
        with transaction() as tx:
            return fail_job(job_id, error, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = CASE
                    WHEN attempts < max_attempts THEN 'retry'
                    ELSE 'failed'
                END,
                error = %s,
                finished_at = CASE
                    WHEN attempts < max_attempts THEN finished_at
                    ELSE NOW()
                END,
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (error[:1000], job_id),
        )
        return cursor.rowcount > 0


def list_runnable_jobs(job_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, object]]:
    query = """
        SELECT job_id, job_type, status, payload, attempts, max_attempts,
               error, created_at, updated_at, started_at, finished_at
        FROM background_jobs
        WHERE status IN ('pending', 'retry')
          AND attempts < max_attempts
    """
    params: list[object] = []
    if job_type:
        query += " AND job_type = %s"
        params.append(job_type)
    query += " ORDER BY id ASC LIMIT %s"
    params.append(max(1, limit))

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [_row_to_job(row) for row in rows]


def cancel_user_extraction_jobs(user_id: str, conn=None) -> int:
    if conn is None:
        with transaction() as tx:
            return cancel_user_extraction_jobs(user_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = 'cancelled',
                error = 'user_companionship_reset',
                finished_at = NOW(),
                updated_at = NOW()
            WHERE job_type = 'memory_extraction'
              AND payload->>'user_id' = %s
              AND status IN ('pending', 'retry', 'running')
            """,
            (user_id,),
        )
        return cursor.rowcount


def reset_running_jobs(job_type: Optional[str] = None, conn=None) -> int:
    if conn is None:
        with transaction() as tx:
            return reset_running_jobs(job_type, conn=tx)

    query = """
        UPDATE background_jobs
        SET status = CASE
                WHEN attempts < max_attempts THEN 'retry'
                ELSE 'failed'
            END,
            updated_at = NOW()
        WHERE status = 'running'
    """
    params: list[object] = []
    if job_type:
        query += " AND job_type = %s"
        params.append(job_type)

    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.rowcount
