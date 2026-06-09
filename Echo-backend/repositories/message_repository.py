import sqlite3
from typing import Dict, List, Optional, Tuple

from db.connection import get_connection, transaction
from repositories.user_repository import upsert_user


def add_message(
    user_id: str,
    role: str,
    content: str,
    conversation_id: Optional[str] = None,
    message_type: str = "text",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    if conn is None:
        with transaction() as tx:
            return add_message(user_id, role, content, conversation_id, message_type, conn=tx)

    upsert_user(user_id=user_id, conn=conn)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chat_messages (user_id, conversation_id, role, content, message_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, conversation_id, role, content, message_type),
    )
    if conversation_id:
        cursor.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND conversation_id = ?
            """,
            (user_id, conversation_id),
        )
    return int(cursor.lastrowid)


def add_chat_turn(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
) -> Tuple[int, int]:
    """Atomically persist the user and assistant messages for one chat turn."""
    with transaction() as conn:
        user_message_id = add_message(
            user_id=user_id,
            role="user",
            content=user_message,
            conversation_id=conversation_id,
            message_type=user_message_type,
            conn=conn,
        )
        assistant_message_id = add_message(
            user_id=user_id,
            role="assistant",
            content=assistant_reply,
            conversation_id=conversation_id,
            message_type=assistant_message_type,
            conn=conn,
        )
        return user_message_id, assistant_message_id


def get_history(
    user_id: str,
    limit: int = 20,
    conversation_id: Optional[str] = None,
    after_message_id: int = 0,
) -> List[Dict[str, str]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if conversation_id:
            cursor.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = ? AND conversation_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, conversation_id, after_message_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = ? AND id > ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, after_message_id, limit),
            )
        rows = cursor.fetchall()

    rows.reverse()
    return [{"role": row[0], "content": row[1]} for row in rows]


def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    after_message_id: int = 0,
) -> List[Dict[str, object]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, role, content, message_type, timestamp
            FROM chat_messages
            WHERE user_id = ? AND conversation_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (user_id, conversation_id, after_message_id),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": int(row[0]),
            "role": row[1],
            "content": row[2],
            "message_type": row[3],
            "timestamp": row[4],
        }
        for row in rows
    ]
