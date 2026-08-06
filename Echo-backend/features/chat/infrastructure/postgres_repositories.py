import json
import uuid

from db.postgres_connection import get_connection, transaction

from features.agent.domain.entities import ContentPart
from features.auth.public import ensure_user_identity


def ensure_conversation(
    user_id: str,
    conversation_id: str | None = None,
    title: str | None = None,
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

            conversation_id = (
                row["conversation_id"] if row else ensure_conversation(user_id, conn=conn)
            )
            cursor.execute(
                """
                UPDATE chat_messages
                SET conversation_id = %s
                WHERE user_id = %s AND conversation_id IS NULL
                """,
                (conversation_id, user_id),
            )
        return conversation_id


def get_conversation_summary(user_id: str, conversation_id: str) -> dict[str, object]:
    with get_connection() as conn, conn.cursor() as cursor:
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
            return update_conversation_summary(
                user_id, conversation_id, summary, summary_message_id, conn=tx
            )

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
    conversation_id: str | None = None,
    message_type: str = "text",
    conn=None,
) -> int:
    if conn is None:
        with transaction() as tx:
            return add_message(user_id, role, content, conversation_id, message_type, conn=tx)

    internal_id, _ = _add_message_record(
        user_id=user_id,
        role=role,
        content=content,
        conversation_id=conversation_id,
        message_type=message_type,
        conn=conn,
    )
    return internal_id


def _add_message_record(
    user_id: str,
    role: str,
    content: str,
    conversation_id: str | None,
    message_type: str,
    conn,
) -> tuple[int, str]:
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
    return int(inserted_row["id"]), message_id


def _add_message_attachments(
    conn,
    user_id: str,
    message_id: str,
    content_parts: tuple[ContentPart, ...],
    position_offset: int,
) -> None:
    sticker_parts = [part for part in content_parts if part.type == "sticker" and part.sticker_id]
    if not sticker_parts:
        return
    with conn.cursor() as cursor:
        for index, part in enumerate(sticker_parts, start=position_offset):
            cursor.execute(
                """
                SELECT description, semantic_tags, public_url
                FROM stickers
                WHERE sticker_id = %s
                  AND status = 'active'
                  AND (owner_type = 'echo' OR owner_user_id = %s)
                """,
                (part.sticker_id, user_id),
            )
            sticker = cursor.fetchone()
            if sticker is None:
                raise ValueError("Sticker attachment is unavailable")
            tags = sticker["semantic_tags"] or []
            if isinstance(tags, str):
                tags = json.loads(tags)
            metadata = {
                "description": str(sticker["description"] or ""),
                "semantic_tags": list(tags),
                "url": str(sticker["public_url"] or part.url or ""),
            }
            cursor.execute(
                """
                INSERT INTO chat_message_attachments (
                    attachment_id, message_id, user_id, attachment_type,
                    resource_id, position, metadata
                ) VALUES (%s, %s, %s, 'sticker', %s, %s, %s::jsonb)
                """,
                (
                    f"att_{uuid.uuid4().hex}",
                    message_id,
                    user_id,
                    part.sticker_id,
                    index,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )


def add_chat_turn(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    user_message_type: str = "text",
    assistant_message_type: str = "text",
    user_content_parts: tuple[ContentPart, ...] = (),
    assistant_content_parts: tuple[ContentPart, ...] = (),
) -> tuple[int, int]:
    with transaction() as conn:
        user_message_id, user_stable_message_id = _add_message_record(
            user_id=user_id,
            role="user",
            content=user_message,
            conversation_id=conversation_id,
            message_type=user_message_type,
            conn=conn,
        )
        _add_message_attachments(
            conn,
            user_id,
            user_stable_message_id,
            user_content_parts,
            position_offset=1 if user_message else 0,
        )
        assistant_message_id, assistant_stable_message_id = _add_message_record(
            user_id=user_id,
            role="assistant",
            content=assistant_reply,
            conversation_id=conversation_id,
            message_type=assistant_message_type,
            conn=conn,
        )
        _add_message_attachments(
            conn,
            user_id,
            assistant_stable_message_id,
            assistant_content_parts,
            position_offset=1 if assistant_reply else 0,
        )
        return user_message_id, assistant_message_id


def count_user_messages(user_id: str, conversation_id: str) -> int:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT COUNT(*) AS message_count
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND role = 'user'
                  AND status = 'active'
                """,
            (user_id, conversation_id),
        )
        row = cursor.fetchone()
    return int(row["message_count"]) if row else 0


def list_recent_user_messages(
    user_id: str,
    conversation_id: str,
    limit: int,
) -> tuple[tuple[int, str], ...]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT id, content
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND role = 'user'
                  AND status = 'active'
                ORDER BY id DESC
                LIMIT %s
                """,
            (user_id, conversation_id, limit),
        )
        rows = cursor.fetchall()
    rows.reverse()
    return tuple((int(row["id"]), str(row["content"])) for row in rows)


def clear_context(user_id: str) -> tuple[int, int]:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                DELETE FROM chat_message_attachments
                WHERE user_id = %s
                   OR message_id IN (
                        SELECT message_id FROM chat_messages WHERE user_id = %s
                   )
                """,
            (user_id, user_id),
        )
        cursor.execute("DELETE FROM chat_messages WHERE user_id = %s", (user_id,))
        deleted_messages = max(cursor.rowcount, 0)

        cursor.execute(
            """
                UPDATE conversations
                SET summary = '',
                    summary_message_id = 0,
                    updated_at = NOW()
                WHERE user_id = %s
                """,
            (user_id,),
        )
        reset_conversations = max(cursor.rowcount, 0)

    return deleted_messages, reset_conversations


def get_history(
    user_id: str,
    limit: int = 20,
    conversation_id: str | None = None,
    after_message_id: int = 0,
) -> list[dict[str, str]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if conversation_id:
                cursor.execute(
                    """
                    SELECT message_id, role, content
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
                    SELECT message_id, role, content
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
        attachments = _load_message_attachments(
            conn,
            [str(row["message_id"] or "") for row in rows],
        )

    rows.reverse()
    return [
        {
            "role": row["role"],
            "content": _render_message_content(
                str(row["content"]),
                attachments.get(str(row["message_id"] or ""), ()),
            ),
        }
        for row in rows
    ]


def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    after_message_id: int = 0,
) -> list[dict[str, object]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, message_id, role, content, message_type, created_at
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
        attachments = _load_message_attachments(
            conn,
            [str(row["message_id"] or "") for row in rows],
        )

    return [
        {
            "id": int(row["id"]),
            "role": row["role"],
            "content": _render_message_content(
                str(row["content"]),
                attachments.get(str(row["message_id"] or ""), ()),
            ),
            "message_type": row["message_type"],
            "timestamp": row["created_at"],
        }
        for row in rows
    ]


def list_messages_page(
    user_id: str,
    conversation_id: str,
    before_id: int | None,
    limit: int,
) -> tuple[list[dict[str, object]], bool]:
    params: list[object] = [user_id, conversation_id]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < %s"
        params.append(before_id)
    params.append(limit + 1)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, message_id, role, content, message_type, created_at
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND status = 'active'
                  {before_clause}
                ORDER BY id DESC
                LIMIT %s
                """,
                params,
            )
            rows = cursor.fetchall()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        attachments = _load_message_attachments(
            conn,
            [str(row["message_id"] or "") for row in page_rows],
        )

    page_rows.reverse()
    return (
        [
            {
                "message_id": int(row["id"]),
                "role": str(row["role"]),
                "content": "" if row["message_type"] == "sticker" else str(row["content"]),
                "message_type": str(row["message_type"]),
                "content_parts": _history_content_parts(
                    attachments.get(str(row["message_id"] or ""), ())
                ),
                "created_at": row["created_at"],
            }
            for row in page_rows
        ],
        has_more,
    )


def has_recent_assistant_sticker(
    user_id: str,
    conversation_id: str,
    assistant_turns: int = 4,
) -> bool:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM (
                    SELECT message_id
                    FROM chat_messages
                    WHERE user_id = %s
                      AND conversation_id = %s
                      AND role = 'assistant'
                      AND status = 'active'
                    ORDER BY id DESC
                    LIMIT %s
                ) recent
                JOIN chat_message_attachments attachment
                  ON attachment.message_id = recent.message_id
                WHERE attachment.attachment_type = 'sticker'
            ) AS has_sticker
            """,
            (user_id, conversation_id, assistant_turns),
        )
        row = cursor.fetchone()
    return bool(row and row["has_sticker"])


def _load_message_attachments(
    conn,
    message_ids: list[str],
) -> dict[str, tuple[dict[str, object], ...]]:
    clean_ids = [message_id for message_id in message_ids if message_id]
    if not clean_ids:
        return {}
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT message_id, attachment_type, resource_id, position, metadata
            FROM chat_message_attachments
            WHERE message_id = ANY(%s)
            ORDER BY message_id, position, id
            """,
            (clean_ids,),
        )
        rows = cursor.fetchall()
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        grouped.setdefault(str(row["message_id"]), []).append(
            {
                "type": str(row["attachment_type"]),
                "resource_id": str(row["resource_id"]),
                "position": int(row["position"]),
                "metadata": metadata,
            }
        )
    return {key: tuple(value) for key, value in grouped.items()}


def _history_content_parts(
    attachments: tuple[dict[str, object], ...],
) -> tuple[ContentPart, ...]:
    parts: list[ContentPart] = []
    for attachment in attachments:
        if attachment.get("type") != "sticker":
            continue
        metadata = attachment.get("metadata") or {}
        parts.append(
            ContentPart(
                type="sticker",
                sticker_id=str(attachment.get("resource_id") or ""),
                url=str(metadata.get("url") or ""),
            )
        )
    return tuple(parts)


def _render_message_content(
    content: str,
    attachments: tuple[dict[str, object], ...],
) -> str:
    if not attachments:
        return content
    lines = [content, "", "[本条消息的可信结构化附件]"]
    for attachment in attachments:
        if attachment.get("type") != "sticker":
            continue
        metadata = attachment.get("metadata") or {}
        description = str(metadata.get("description") or "未提供")
        tags = metadata.get("semantic_tags") or []
        tag_text = "、".join(str(tag) for tag in tags) or "未提供"
        lines.append(
            f"- 表情包 {attachment.get('resource_id')}：描述={description}；语义标签={tag_text}"
        )
    return "\n".join(lines).strip()


def claim_chat_request(
    user_id: str,
    request_id: str,
    request_fingerprint: str,
) -> tuple[str, dict[str, object] | None]:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chat_request_results (
                user_id, request_id, request_fingerprint, status
            ) VALUES (%s, %s, %s, 'processing')
            ON CONFLICT (user_id, request_id) DO NOTHING
            """,
            (user_id, request_id, request_fingerprint),
        )
        if cursor.rowcount == 1:
            return "claimed", None

        cursor.execute(
            """
            SELECT request_fingerprint, status, response_payload
            FROM chat_request_results
            WHERE user_id = %s AND request_id = %s
            FOR UPDATE
            """,
            (user_id, request_id),
        )
        row = cursor.fetchone()
        if row is None:
            return "in_progress", None
        if row["request_fingerprint"] != request_fingerprint:
            return "conflict", None
        if row["status"] == "completed" and row["response_payload"] is not None:
            payload = row["response_payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return "completed", dict(payload)

        cursor.execute(
            """
            UPDATE chat_request_results
            SET status = 'processing', error_code = NULL, updated_at = NOW()
            WHERE user_id = %s
              AND request_id = %s
              AND status = 'processing'
              AND updated_at < NOW() - INTERVAL '5 minutes'
            """,
            (user_id, request_id),
        )
        return ("claimed", None) if cursor.rowcount == 1 else ("in_progress", None)


def complete_chat_request(
    user_id: str,
    request_id: str,
    request_fingerprint: str,
    response_payload: dict[str, object],
) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE chat_request_results
            SET status = 'completed', response_payload = %s::jsonb,
                error_code = NULL, updated_at = NOW()
            WHERE user_id = %s
              AND request_id = %s
              AND request_fingerprint = %s
              AND status = 'processing'
            """,
            (
                json.dumps(response_payload, ensure_ascii=False),
                user_id,
                request_id,
                request_fingerprint,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Chat request result could not be completed")


def abandon_chat_request(
    user_id: str,
    request_id: str,
    request_fingerprint: str,
) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM chat_request_results
            WHERE user_id = %s
              AND request_id = %s
              AND request_fingerprint = %s
              AND status = 'processing'
            """,
            (user_id, request_id, request_fingerprint),
        )
