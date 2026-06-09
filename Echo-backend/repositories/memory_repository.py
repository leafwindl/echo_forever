import sqlite3
import uuid
from typing import Dict, List, Optional

from db.connection import get_connection, transaction
from repositories.user_repository import upsert_user


def _row_to_memory(row) -> Dict[str, object]:
    return {
        "memory_id": row[0],
        "user_id": row[1],
        "memory_type": row[2],
        "content": row[3],
        "source_message_id": row[4],
        "confidence": float(row[5] or 0),
        "importance": int(row[6] or 0),
        "status": row[7],
        "created_at": row[8],
        "updated_at": row[9],
        "expires_at": row[10],
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
        WHERE user_id = ?
    """
    params: list[object] = [user_id]

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY importance DESC, updated_at DESC, id DESC"
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [_row_to_memory(row) for row in rows]


def get_user_memory(user_id: str, memory_id: str) -> Optional[Dict[str, object]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                memory_id, user_id, memory_type, content, source_message_id,
                confidence, importance, status, created_at, updated_at, expires_at
            FROM user_memories
            WHERE user_id = ? AND memory_id = ?
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
    conn: Optional[sqlite3.Connection] = None,
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

    upsert_user(user_id=user_id, conn=conn)
    memory_id = f"mem_{uuid.uuid4().hex}"
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_memories (
            memory_id, user_id, memory_type, content,
            source_message_id, confidence, importance
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
    conn: Optional[sqlite3.Connection] = None,
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

    assignments = ["updated_at = CURRENT_TIMESTAMP"]
    params: list[object] = []

    if memory_type is not None:
        assignments.append("memory_type = ?")
        params.append(memory_type)
    if content is not None:
        clean_content = content.strip()
        if not clean_content:
            return False
        assignments.append("content = ?")
        params.append(clean_content)
    if source_message_id is not None:
        assignments.append("source_message_id = ?")
        params.append(source_message_id)
    if confidence is not None:
        assignments.append("confidence = ?")
        params.append(confidence)
    if importance is not None:
        assignments.append("importance = ?")
        params.append(importance)
    if status is not None:
        assignments.append("status = ?")
        params.append(status)

    params.extend([user_id, memory_id])
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE user_memories
        SET {", ".join(assignments)}
        WHERE user_id = ? AND memory_id = ?
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


def clear_user_memories(user_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    if conn is None:
        with transaction() as tx:
            return clear_user_memories(user_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE user_memories
        SET status = 'deleted',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND (status IS NULL OR status != 'deleted')
        """,
        (user_id,),
    )
    return cursor.rowcount
