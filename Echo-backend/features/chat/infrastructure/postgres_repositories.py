import json
import uuid
from datetime import UTC, datetime

from db.postgres_connection import get_connection, transaction
from shared.config import settings

from features.agent.domain.entities import ContentPart, SourceReference
from features.auth.public import ensure_user_identity
from features.stickers.public import resolve_sticker_asset_url


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


def get_or_create_active_conversation(user_id: str, conn=None) -> str:
    if conn is None:
        with transaction() as tx:
            return get_or_create_active_conversation(user_id, conn=tx)

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
    client_message_id: str | None = None,
    agent_turn_id: str | None = None,
    reply_group_id: str | None = None,
    sequence_in_group: int = 0,
    in_reply_to_message_id: int | None = None,
) -> tuple[int, str]:
    ensure_user_identity(user_id=user_id, conn=conn)
    message_id = f"msg_{uuid.uuid4().hex}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chat_messages (
                message_id, client_message_id, user_id, conversation_id, role,
                content, message_type, agent_turn_id, reply_group_id,
                sequence_in_group, in_reply_to_message_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                message_id,
                client_message_id,
                user_id,
                conversation_id,
                role,
                content,
                message_type,
                agent_turn_id,
                reply_group_id,
                sequence_in_group,
                in_reply_to_message_id,
            ),
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
            UPDATE chat_turn_jobs
            SET status = 'cancelled', lease_expires_at = NULL,
                completed_at = NOW(), updated_at = NOW(),
                error_code = 'conversation_cleared'
            WHERE user_id = %s
              AND status IN ('collecting', 'queued', 'running')
            """,
            (user_id,),
        )
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
    before_message_id: int | None = None,
) -> list[dict[str, str]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            before_clause = "AND id < %s" if before_message_id is not None else ""
            if conversation_id:
                params: list[object] = [user_id, conversation_id, after_message_id]
                if before_message_id is not None:
                    params.append(before_message_id)
                params.append(limit)
                cursor.execute(
                    f"""
                    SELECT message_id, role, content
                    FROM chat_messages
                    WHERE user_id = %s
                      AND conversation_id = %s
                      AND id > %s
                      {before_clause}
                      AND status = 'active'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    params,
                )
            else:
                params = [user_id, after_message_id]
                if before_message_id is not None:
                    params.append(before_message_id)
                params.append(limit)
                cursor.execute(
                    f"""
                    SELECT message_id, role, content
                    FROM chat_messages
                    WHERE user_id = %s
                      AND id > %s
                      {before_clause}
                      AND status = 'active'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    params,
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
    after_id: int | None,
    limit: int,
) -> tuple[list[dict[str, object]], bool]:
    params: list[object] = [user_id, conversation_id]
    cursor_clause = ""
    order_direction = "DESC"
    if before_id is not None:
        cursor_clause = "AND id < %s"
        params.append(before_id)
    elif after_id is not None:
        cursor_clause = "AND id > %s"
        order_direction = "ASC"
        params.append(after_id)
    params.append(limit + 1)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, message_id, client_message_id, role, content,
                       message_type, agent_turn_id, reply_group_id,
                       sequence_in_group, in_reply_to_message_id, created_at
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND status = 'active'
                  {cursor_clause}
                ORDER BY id {order_direction}
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

    if after_id is None:
        page_rows.reverse()
    return (
        [
            {
                "message_id": int(row["id"]),
                "stable_message_id": str(row["message_id"] or ""),
                "client_message_id": str(row["client_message_id"] or ""),
                "role": str(row["role"]),
                "content": "" if row["message_type"] == "sticker" else str(row["content"]),
                "message_type": str(row["message_type"]),
                "content_parts": _history_content_parts(
                    attachments.get(str(row["message_id"] or ""), ())
                ),
                "sources": _history_sources(
                    attachments.get(str(row["message_id"] or ""), ())
                ),
                "agent_turn_id": str(row["agent_turn_id"] or ""),
                "reply_group_id": str(row["reply_group_id"] or ""),
                "sequence_in_group": int(row["sequence_in_group"] or 0),
                "in_reply_to_message_id": (
                    int(row["in_reply_to_message_id"])
                    if row["in_reply_to_message_id"] is not None
                    else None
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
    assistant_turns: int = 2,
    minimum_interval_seconds: int = 30,
) -> bool:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            WITH recent_groups AS (
                SELECT COALESCE(NULLIF(reply_group_id, ''), message_id) AS group_id,
                       MAX(id) AS latest_id
                FROM chat_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND role = 'assistant'
                  AND status = 'active'
                GROUP BY COALESCE(NULLIF(reply_group_id, ''), message_id)
                ORDER BY latest_id DESC
                LIMIT %s
            ), recent_messages AS (
                SELECT message.message_id
                FROM chat_messages message
                JOIN recent_groups recent
                  ON COALESCE(NULLIF(message.reply_group_id, ''), message.message_id)
                   = recent.group_id
                WHERE message.user_id = %s
                  AND message.conversation_id = %s
                  AND message.role = 'assistant'
                  AND message.status = 'active'
            )
            SELECT EXISTS (
                SELECT 1 FROM recent_messages recent
                JOIN chat_message_attachments attachment
                  ON attachment.message_id = recent.message_id
                WHERE attachment.attachment_type = 'sticker'
                UNION ALL
                SELECT 1
                FROM chat_messages message
                JOIN chat_message_attachments attachment
                  ON attachment.message_id = message.message_id
                WHERE message.user_id = %s
                  AND message.conversation_id = %s
                  AND message.role = 'assistant'
                  AND message.status = 'active'
                  AND attachment.attachment_type = 'sticker'
                  AND message.created_at >= NOW() - (%s * INTERVAL '1 second')
            ) AS has_sticker
            """,
            (
                user_id,
                conversation_id,
                assistant_turns,
                user_id,
                conversation_id,
                user_id,
                conversation_id,
                minimum_interval_seconds,
            ),
        )
        row = cursor.fetchone()
    return bool(row and row["has_sticker"])


def get_conversation_timing(
    user_id: str,
    conversation_id: str | None,
    *,
    current_message_id: int | None = None,
) -> dict[str, object] | None:
    if not conversation_id:
        return None
    with get_connection() as conn, conn.cursor() as cursor:
        current_at = datetime.now(UTC)
        before_clause = ""
        params: list[object] = [user_id, conversation_id]
        if current_message_id is not None:
            cursor.execute(
                """
                SELECT created_at
                FROM chat_messages
                WHERE user_id = %s AND conversation_id = %s AND id = %s
                """,
                (user_id, conversation_id, current_message_id),
            )
            current_row = cursor.fetchone()
            if current_row is not None:
                current_at = current_row["created_at"]
            before_clause = "AND id < %s"
            params.append(current_message_id)
        cursor.execute(
            f"""
            SELECT created_at
            FROM chat_messages
            WHERE user_id = %s
              AND conversation_id = %s
              AND role = 'user'
              AND status = 'active'
              {before_clause}
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        )
        previous = cursor.fetchone()
    if previous is None:
        return None
    previous_at = previous["created_at"]
    if current_at.tzinfo is None:
        current_at = current_at.replace(tzinfo=UTC)
    if previous_at.tzinfo is None:
        previous_at = previous_at.replace(tzinfo=UTC)
    gap_seconds = max(int((current_at - previous_at).total_seconds()), 0)
    state = classify_conversation_gap(gap_seconds)
    return {
        "gap_seconds": gap_seconds,
        "state": state,
        "should_acknowledge_gap": state in {"returned", "long_absence"},
    }


def classify_conversation_gap(gap_seconds: int) -> str:
    if gap_seconds <= settings.conversation_active_max_seconds:
        return "active"
    if gap_seconds < settings.conversation_returned_min_seconds:
        return "recent"
    if gap_seconds < settings.conversation_long_absence_seconds:
        return "returned"
    return "long_absence"


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
            SELECT attachment.message_id, attachment.attachment_type,
                   attachment.resource_id, attachment.position, attachment.metadata,
                   sticker.source AS sticker_source,
                   sticker.storage_key AS sticker_storage_key,
                   sticker.public_url AS sticker_public_url
            FROM chat_message_attachments attachment
            LEFT JOIN stickers sticker
              ON attachment.attachment_type = 'sticker'
             AND sticker.sticker_id = attachment.resource_id
            WHERE attachment.message_id = ANY(%s)
            ORDER BY attachment.message_id, attachment.position, attachment.id
            """,
            (clean_ids,),
        )
        rows = cursor.fetchall()
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        metadata = dict(metadata)
        if str(row["attachment_type"]) == "sticker" and row["sticker_storage_key"]:
            metadata["url"] = resolve_sticker_asset_url(
                source=str(row["sticker_source"] or ""),
                storage_key=str(row["sticker_storage_key"] or ""),
                public_url=str(row["sticker_public_url"] or metadata.get("url") or ""),
            )
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


def _history_sources(
    attachments: tuple[dict[str, object], ...],
) -> tuple[SourceReference, ...]:
    sources: list[SourceReference] = []
    for attachment in attachments:
        if attachment.get("type") != "source":
            continue
        metadata = attachment.get("metadata") or {}
        sources.append(
            SourceReference(
                title=str(metadata.get("title") or "来源"),
                url=str(metadata.get("url") or ""),
                snippet=str(metadata.get("snippet") or ""),
                published_at=(
                    str(metadata.get("published_at"))
                    if metadata.get("published_at")
                    else None
                ),
            )
        )
    return tuple(sources)


def _add_source_attachments(
    conn,
    user_id: str,
    message_id: str,
    sources: tuple[SourceReference, ...],
    position_offset: int = 0,
) -> None:
    if not sources:
        return
    with conn.cursor() as cursor:
        for index, source in enumerate(sources, start=position_offset):
            metadata = {
                "title": source.title,
                "url": source.url,
                "snippet": source.snippet,
                "published_at": source.published_at,
            }
            cursor.execute(
                """
                INSERT INTO chat_message_attachments (
                    attachment_id, message_id, user_id, attachment_type,
                    resource_id, position, metadata
                ) VALUES (%s, %s, %s, 'source', %s, %s, %s::jsonb)
                """,
                (
                    f"att_{uuid.uuid4().hex}",
                    message_id,
                    user_id,
                    source.url,
                    index,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )


def _render_message_content(
    content: str,
    attachments: tuple[dict[str, object], ...],
    *,
    include_sticker_descriptions: bool = True,
) -> str:
    if not attachments:
        return content
    lines = [content, "", "[本条消息的可信结构化附件]"]
    for attachment in attachments:
        if attachment.get("type") != "sticker":
            continue
        metadata = attachment.get("metadata") or {}
        description = str(metadata.get("description") or "").strip()
        tags = metadata.get("semantic_tags") or []
        tag_text = "、".join(str(tag) for tag in tags) or "未提供"
        if include_sticker_descriptions and description:
            lines.append(
                f"- 表情包 {attachment.get('resource_id')}：描述={description}；语义标签={tag_text}"
            )
        else:
            lines.append(f"- 表情包语义标签={tag_text}")
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
