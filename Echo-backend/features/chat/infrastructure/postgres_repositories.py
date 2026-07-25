import uuid
from typing import Dict, List, Optional, Tuple

from db.postgres_connection import get_connection, transaction
from features.auth.public import ensure_user_identity


def ensure_conversation(
    user_id: str,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None,
    conn=None,
) -> str:
    if conn is None:
        with transaction() as tx:
            return ensure_conversation(user_id, conversation_id, title, conn=tx)

    ensure_user_identity(user_id=user_id, conn=conn)
    resolved_id = conversation_id or f"conv_{uuid.uuid4().hex}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations (conversation_id, user_id, title)
            VALUES (%s, %s, %s)
            ON CONFLICT(conversation_id) DO NOTHING
            """,
            (resolved_id, user_id, title),
        )
    return resolved_id


def get_or_create_active_conversation(user_id: str) -> str:
    with transaction() as conn:
        ensure_user_identity(user_id=user_id, conn=conn)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT conversation_id
                FROM conversations
                WHERE user_id = %s AND status = 'active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()

            conversation_id = row["conversation_id"] if row else ensure_conversation(user_id, conn=conn)
            cursor.execute(
                """
                UPDATE chat_messages
                SET conversation_id = %s
                WHERE user_id = %s AND conversation_id IS NULL
                """,
                (conversation_id, user_id),
            )
        return conversation_id


def get_conversation_summary(user_id: str, conversation_id: str) -> Dict[str, object]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT summary, COALESCE(summary_message_id, 0) AS summary_message_id
                FROM conversations
                WHERE user_id = %s AND conversation_id = %s
                """,
                (user_id, conversation_id),
            )
            row = cursor.fetchone()

    if not row:
        return {"summary": "", "summary_message_id": 0}

    return {
        "summary": row["summary"] or "",
        "summary_message_id": int(row["summary_message_id"] or 0),
    }


def update_conversation_summary(
    user_id: str,
    conversation_id: str,
    summary: str,
    summary_message_id: int,
    conn=None,
) -> None:
    if conn is None:
        with transaction() as tx:
            return update_conversation_summary(user_id, conversation_id, summary, summary_message_id, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE conversations
            SET summary = %s,
                summary_message_id = %s,
                updated_at = NOW()
            WHERE user_id = %s AND conversation_id = %s
            """,
            (summary, summary_message_id, user_id, conversation_id),
        )


def add_message(
    user_id: str,
    role: str,
    content: str,
    conversation_id: Optional[str] = None,
    message_type: str = "text",
    conn=None,
) -> int:
    if conn is None:
        with transaction() as tx:
            return add_message(user_id, role, content, conversation_id, message_type, conn=tx)

    ensure_user_identity(user_id=user_id, conn=conn)
    message_id = f"msg_{uuid.uuid4().hex}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chat_messages (
                message_id, user_id, conversation_id, role, content, message_type
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (message_id, user_id, conversation_id, role, content, message_type),
        )
        inserted_row = cursor.fetchone()
        if conversation_id:
            cursor.execute(
                """
                UPDATE conversations
                SET updated_at = NOW()
                WHERE user_id = %s AND conversation_id = %s
                """,
                (user_id, conversation_id),
            )
    return int(inserted_row["id"])


def add_chat_turn(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
) -> Tuple[int, int]:
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
        with conn.cursor() as cursor:
            if conversation_id:
                cursor.execute(
                    """
                    SELECT role, content
                    FROM chat_messages
                    WHERE user_id = %s
                      AND conversation_id = %s
                      AND id > %s
                      AND status = 'active'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (user_id, conversation_id, after_message_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT role, content
                    FROM chat_messages
                    WHERE user_id = %s
                      AND id > %s
                      AND status = 'active'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (user_id, after_message_id, limit),
                )
            rows = cursor.fetchall()

    rows.reverse()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    after_message_id: int = 0,
) -> List[Dict[str, object]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, message_type, created_at
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND id > %s
                  AND status = 'active'
                ORDER BY id ASC
                """,
                (user_id, conversation_id, after_message_id),
            )
            rows = cursor.fetchall()

    return [
        {
            "id": int(row["id"]),
            "role": row["role"],
            "content": row["content"],
            "message_type": row["message_type"],
            "timestamp": row["created_at"],
        }
        for row in rows
    ]
