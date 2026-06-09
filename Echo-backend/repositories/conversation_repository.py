import sqlite3
import uuid
from typing import Dict, Optional

from db.connection import get_connection, transaction
from repositories.user_repository import upsert_user


def ensure_conversation(
    user_id: str,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    if conn is None:
        with transaction() as tx:
            return ensure_conversation(user_id, conversation_id, title, conn=tx)

    upsert_user(user_id=user_id, conn=conn)
    resolved_id = conversation_id or f"conv_{uuid.uuid4().hex}"
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO conversations (conversation_id, user_id, title)
        VALUES (?, ?, ?)
        """,
        (resolved_id, user_id, title),
    )
    return resolved_id


def get_or_create_active_conversation(user_id: str) -> str:
    with transaction() as conn:
        upsert_user(user_id=user_id, conn=conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT conversation_id
            FROM conversations
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()

        conversation_id = row[0] if row else ensure_conversation(user_id, conn=conn)
        cursor.execute(
            """
            UPDATE chat_messages
            SET conversation_id = ?
            WHERE user_id = ? AND conversation_id IS NULL
            """,
            (conversation_id, user_id),
        )
        return conversation_id


def get_conversation_summary(user_id: str, conversation_id: str) -> Dict[str, object]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT summary, COALESCE(summary_message_id, 0)
            FROM conversations
            WHERE user_id = ? AND conversation_id = ?
            """,
            (user_id, conversation_id),
        )
        row = cursor.fetchone()

    if not row:
        return {"summary": "", "summary_message_id": 0}

    return {"summary": row[0] or "", "summary_message_id": int(row[1] or 0)}


def update_conversation_summary(
    user_id: str,
    conversation_id: str,
    summary: str,
    summary_message_id: int,
    conn: Optional[sqlite3.Connection] = None,
):
    if conn is None:
        with transaction() as tx:
            return update_conversation_summary(user_id, conversation_id, summary, summary_message_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversations
        SET summary = ?,
            summary_message_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND conversation_id = ?
        """,
        (summary, summary_message_id, user_id, conversation_id),
    )
