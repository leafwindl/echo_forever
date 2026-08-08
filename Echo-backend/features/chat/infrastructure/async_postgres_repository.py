from __future__ import annotations

import uuid

from db.postgres_connection import get_connection, transaction

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    ChatAcceptedTurn,
    ChatBatchInput,
    ChatDeliveryPresentation,
    ChatHistoryMessage,
    ChatMessageAcceptance,
    ChatQueueFullError,
    ChatReplyGroup,
    ChatTurnJob,
    ChatTurnStatus,
    PreparedChatReply,
)
from features.chat.infrastructure import postgres_repositories


class PostgresAsyncChatRepository:
    def accept_message(
        self,
        *,
        user_id: str,
        client_message_id: str,
        message_type: str,
        content: str,
        content_parts: tuple[ContentPart, ...],
        quiet_window_ms: int,
        maximum_window_ms: int,
        maximum_batch_messages: int,
        maximum_batch_characters: int,
        maximum_queued_messages: int,
    ) -> ChatMessageAcceptance:
        with transaction() as conn:
            conversation_id = postgres_repositories.get_or_create_active_conversation(
                user_id,
                conn=conn,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT conversation_id
                    FROM conversations
                    WHERE user_id = %s AND conversation_id = %s
                    FOR UPDATE
                    """,
                    (user_id, conversation_id),
                )
                if cursor.fetchone() is None:
                    raise ValueError("Active conversation is unavailable")

                existing = self._find_existing_message(
                    conn,
                    user_id,
                    client_message_id,
                )
                if existing is not None:
                    existing_parts = tuple(
                        (part.type, part.sticker_id, part.url)
                        for part in existing.content_parts
                    )
                    incoming_parts = tuple(
                        (part.type, part.sticker_id, part.url) for part in content_parts
                    )
                    if (
                        existing.message_type != message_type
                        or existing.content != ("" if message_type == "sticker" else content)
                        or existing_parts != incoming_parts
                    ):
                        raise ValueError(
                            "client_message_id cannot be reused with different chat content"
                        )
                    turn = self._turn_for_message(conn, existing.agent_turn_id)
                    return ChatMessageAcceptance(
                        conversation_id=conversation_id,
                        message=existing,
                        turn=turn,
                        replayed=True,
                    )

                cursor.execute(
                    """
                    SELECT COALESCE(SUM(message_count), 0) AS queued_count
                    FROM chat_turn_jobs
                    WHERE user_id = %s
                      AND conversation_id = %s
                      AND status IN ('collecting', 'queued', 'running')
                    """,
                    (user_id, conversation_id),
                )
                row = cursor.fetchone()
                if int(row["queued_count"] if row else 0) >= maximum_queued_messages:
                    raise ChatQueueFullError("Too many chat messages are waiting")

            visible_content = "" if message_type == "sticker" else content
            internal_id, stable_message_id = postgres_repositories._add_message_record(
                user_id=user_id,
                role="user",
                content=visible_content,
                conversation_id=conversation_id,
                message_type=message_type,
                conn=conn,
                client_message_id=client_message_id,
            )
            postgres_repositories._add_message_attachments(
                conn,
                user_id,
                stable_message_id,
                content_parts,
                position_offset=1 if visible_content else 0,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE proactive_chat_preferences
                    SET consecutive_unanswered = 0, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )

            character_count = len(content)
            turn_id, turn_status = self._append_or_create_turn(
                conn=conn,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=internal_id,
                character_count=character_count,
                quiet_window_ms=quiet_window_ms,
                maximum_window_ms=maximum_window_ms,
                maximum_batch_messages=maximum_batch_messages,
                maximum_batch_characters=maximum_batch_characters,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE chat_messages
                    SET agent_turn_id = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (turn_id, internal_id, user_id),
                )
                cursor.execute(
                    "SELECT created_at FROM chat_messages WHERE id = %s",
                    (internal_id,),
                )
                created_row = cursor.fetchone()

            return ChatMessageAcceptance(
                conversation_id=conversation_id,
                message=ChatHistoryMessage(
                    message_id=internal_id,
                    stable_message_id=stable_message_id,
                    client_message_id=client_message_id,
                    role="user",
                    message_type=message_type,
                    content=visible_content,
                    content_parts=content_parts,
                    created_at=created_row["created_at"],
                    agent_turn_id=turn_id,
                ),
                turn=ChatAcceptedTurn(turn_id=turn_id, status=turn_status),
            )

    def claim_due_turn(self, lease_seconds: int) -> ChatTurnJob | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_turn_jobs
                SET status = CASE
                        WHEN attempt_count < max_attempts THEN 'queued'
                        ELSE 'failed'
                    END,
                    error_code = CASE
                        WHEN attempt_count < max_attempts THEN NULL
                        ELSE 'worker_lease_expired'
                    END,
                    lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE status = 'running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < NOW()
                """
            )
            cursor.execute(
                """
                SELECT job.*
                FROM chat_turn_jobs job
                WHERE job.status IN ('collecting', 'queued')
                  AND (job.status = 'queued' OR job.collect_until <= NOW())
                  AND NOT EXISTS (
                      SELECT 1
                      FROM chat_turn_jobs active
                      WHERE active.conversation_id = job.conversation_id
                        AND active.status = 'running'
                  )
                ORDER BY job.collect_until ASC, job.id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                UPDATE chat_turn_jobs
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    started_at = NOW(),
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW(),
                    error_code = NULL
                WHERE turn_id = %s
                RETURNING *
                """,
                (lease_seconds, row["turn_id"]),
            )
            claimed = cursor.fetchone()
        return self._turn_job(claimed) if claimed else None

    def load_batch(self, turn: ChatTurnJob) -> ChatBatchInput:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, message_id, client_message_id, role, content,
                           message_type, agent_turn_id, reply_group_id,
                           sequence_in_group, in_reply_to_message_id, created_at
                    FROM chat_messages
                    WHERE user_id = %s
                      AND conversation_id = %s
                      AND agent_turn_id = %s
                      AND role = 'user'
                      AND status = 'active'
                    ORDER BY id ASC
                    """,
                    (turn.user_id, turn.conversation_id, turn.turn_id),
                )
                rows = cursor.fetchall()
            attachments = postgres_repositories._load_message_attachments(
                conn,
                [str(row["message_id"] or "") for row in rows],
            )

        messages = tuple(
            self._history_message(
                row,
                attachments.get(str(row["message_id"] or ""), ()),
            )
            for row in rows
        )
        batch_has_text = any(message.content.strip() for message in messages)
        rendered = [
            postgres_repositories._render_message_content(
                message.content,
                attachments.get(message.stable_message_id, ()),
                include_sticker_descriptions=not batch_has_text,
            )
            for message in messages
        ]
        if len(rendered) == 1:
            combined_content = rendered[0]
        else:
            lines = ["用户连续发送了以下消息，请按顺序整体理解并自然回复："]
            lines.extend(f"{index}. {value}" for index, value in enumerate(rendered, start=1))
            combined_content = "\n".join(lines)

        sticker_intents: list[str] = []
        for message in messages:
            for attachment in attachments.get(message.stable_message_id, ()):
                if attachment.get("type") != "sticker":
                    continue
                metadata = attachment.get("metadata") or {}
                tags = " ".join(str(tag) for tag in metadata.get("semantic_tags") or [])
                description = str(metadata.get("description") or "").strip()
                intent = tags if batch_has_text else " ".join(
                    part for part in (description, tags) if part
                )
                if intent:
                    sticker_intents.append(intent)

        return ChatBatchInput(
            turn=turn,
            messages=messages,
            combined_content=combined_content,
            sticker_intent="；".join(sticker_intents),
        )

    def complete_turn(
        self,
        turn: ChatTurnJob,
        reply: PreparedChatReply,
        presentation: ChatDeliveryPresentation,
    ) -> ChatReplyGroup | None:
        reply_group_id = f"reply_{uuid.uuid4().hex}"
        with transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
                    FROM chat_turn_jobs
                    WHERE turn_id = %s
                    FOR UPDATE
                    """,
                    (turn.turn_id,),
                )
                current = cursor.fetchone()
                if current is None or current["status"] != "running":
                    return None

            text_segments = tuple(
                segment.strip()
                for segment in reply.reply_segments
                if segment.strip()
            )
            if not text_segments and reply.reply.strip():
                text_segments = (reply.reply.strip(),)
            sticker_parts = tuple(
                part for part in reply.content_parts if part.type == "sticker" and part.sticker_id
            )[:1]
            deliveries: list[tuple[str, str, tuple[ContentPart, ...]]] = []
            if sticker_parts and reply.sticker_placement == "before_text":
                deliveries.append(("sticker", "", sticker_parts))
            deliveries.extend(("text", segment, ()) for segment in text_segments)
            if sticker_parts and reply.sticker_placement != "before_text":
                deliveries.append(("sticker", "", sticker_parts))
            if not deliveries:
                deliveries.append(("text", "刚才这次回复没有完成，再和我说一次好吗？", ()))

            created_messages: list[ChatHistoryMessage] = []
            last_text_index = max(
                (index for index, delivery in enumerate(deliveries) if delivery[0] == "text"),
                default=-1,
            )
            for sequence, (message_type, content, parts) in enumerate(deliveries):
                internal_id, stable_message_id = postgres_repositories._add_message_record(
                    user_id=turn.user_id,
                    role="assistant",
                    content=content,
                    conversation_id=turn.conversation_id,
                    message_type=message_type,
                    conn=conn,
                    agent_turn_id=turn.turn_id,
                    reply_group_id=reply_group_id,
                    sequence_in_group=sequence,
                    in_reply_to_message_id=turn.input_last_message_id,
                )
                postgres_repositories._add_message_attachments(
                    conn,
                    turn.user_id,
                    stable_message_id,
                    parts,
                    position_offset=1 if content else 0,
                )
                message_sources = reply.sources if sequence == last_text_index else ()
                postgres_repositories._add_source_attachments(
                    conn,
                    turn.user_id,
                    stable_message_id,
                    message_sources,
                    position_offset=1 if content else 0,
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT created_at FROM chat_messages WHERE id = %s",
                        (internal_id,),
                    )
                    row = cursor.fetchone()
                created_messages.append(
                    ChatHistoryMessage(
                        message_id=internal_id,
                        stable_message_id=stable_message_id,
                        role="assistant",
                        message_type=message_type,
                        content=content,
                        content_parts=parts,
                        sources=message_sources,
                        created_at=row["created_at"],
                        agent_turn_id=turn.turn_id,
                        reply_group_id=reply_group_id,
                        sequence_in_group=sequence,
                        in_reply_to_message_id=turn.input_last_message_id,
                    )
                )

            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE chat_turn_jobs
                    SET status = 'completed',
                        agent_run_id = %s,
                        reply_group_id = %s,
                        lease_expires_at = NULL,
                        completed_at = NOW(),
                        updated_at = NOW(),
                        error_code = %s
                    WHERE turn_id = %s AND status = 'running'
                    """,
                    (reply.run_id or None, reply_group_id, reply.error_code, turn.turn_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Chat turn completion lost its running lease")

        normalized_delays = tuple(presentation.message_delays_ms[: len(created_messages)])
        if len(normalized_delays) < len(created_messages):
            normalized_delays += (0,) * (len(created_messages) - len(normalized_delays))
        normalized_presentation = ChatDeliveryPresentation(
            agent_elapsed_ms=presentation.agent_elapsed_ms,
            initial_delay_ms=presentation.initial_delay_ms,
            message_delays_ms=normalized_delays,
        )
        return ChatReplyGroup(
            turn_id=turn.turn_id,
            reply_group_id=reply_group_id,
            conversation_id=turn.conversation_id,
            messages=tuple(created_messages),
            presentation=normalized_presentation,
        )

    def fail_turn(self, turn_id: str, error_code: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_turn_jobs
                SET status = 'failed', error_code = %s,
                    lease_expires_at = NULL, completed_at = NOW(), updated_at = NOW()
                WHERE turn_id = %s AND status = 'running'
                """,
                (error_code[:120], turn_id),
            )
            return cursor.rowcount == 1

    def reschedule_turn(self, turn_id: str, delay_ms: int) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_turn_jobs
                SET status = 'queued',
                    collect_until = NOW() + (%s * INTERVAL '1 millisecond'),
                    lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE turn_id = %s AND status = 'running'
                """,
                (max(delay_ms, 0), turn_id),
            )
            return cursor.rowcount == 1

    def has_running_turn(self, user_id: str, conversation_id: str) -> bool:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM chat_turn_jobs
                    WHERE user_id = %s AND conversation_id = %s AND status = 'running'
                ) AS active
                """,
                (user_id, conversation_id),
            )
            row = cursor.fetchone()
        return bool(row and row["active"])

    @staticmethod
    def _append_or_create_turn(
        *,
        conn,
        user_id: str,
        conversation_id: str,
        message_id: int,
        character_count: int,
        quiet_window_ms: int,
        maximum_window_ms: int,
        maximum_batch_messages: int,
        maximum_batch_characters: int,
    ) -> tuple[str, ChatTurnStatus]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM chat_turn_jobs
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND status = 'collecting'
                  AND collect_until > NOW()
                  AND collect_deadline > NOW()
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (user_id, conversation_id),
            )
            row = cursor.fetchone()
            can_append = bool(
                row
                and int(row["message_count"]) < maximum_batch_messages
                and int(row["character_count"]) + character_count
                <= maximum_batch_characters
            )
            if can_append:
                new_count = int(row["message_count"]) + 1
                new_characters = int(row["character_count"]) + character_count
                close_now = (
                    new_count >= maximum_batch_messages
                    or new_characters >= maximum_batch_characters
                )
                cursor.execute(
                    """
                    UPDATE chat_turn_jobs
                    SET input_last_message_id = %s,
                        message_count = %s,
                        character_count = %s,
                        collect_until = CASE
                            WHEN %s THEN NOW()
                            ELSE LEAST(
                                collect_deadline,
                                NOW() + (%s * INTERVAL '1 millisecond')
                            )
                        END,
                        updated_at = NOW()
                    WHERE turn_id = %s
                    """,
                    (
                        message_id,
                        new_count,
                        new_characters,
                        close_now,
                        quiet_window_ms,
                        row["turn_id"],
                    ),
                )
                return str(row["turn_id"]), ChatTurnStatus.COLLECTING

            turn_id = f"turn_{uuid.uuid4().hex}"
            cursor.execute(
                """
                INSERT INTO chat_turn_jobs (
                    turn_id, user_id, conversation_id, status,
                    input_first_message_id, input_last_message_id,
                    message_count, character_count, collect_until, collect_deadline
                ) VALUES (
                    %s, %s, %s, 'collecting', %s, %s, 1, %s,
                    NOW() + (%s * INTERVAL '1 millisecond'),
                    NOW() + (%s * INTERVAL '1 millisecond')
                )
                """,
                (
                    turn_id,
                    user_id,
                    conversation_id,
                    message_id,
                    message_id,
                    character_count,
                    min(quiet_window_ms, maximum_window_ms),
                    maximum_window_ms,
                ),
            )
            return turn_id, ChatTurnStatus.COLLECTING

    @staticmethod
    def _find_existing_message(conn, user_id: str, client_message_id: str):
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, message_id, client_message_id, role, content,
                       message_type, agent_turn_id, reply_group_id,
                       sequence_in_group, in_reply_to_message_id, created_at
                FROM chat_messages
                WHERE user_id = %s AND client_message_id = %s
                """,
                (user_id, client_message_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        attachments = postgres_repositories._load_message_attachments(
            conn,
            [str(row["message_id"] or "")],
        )
        return PostgresAsyncChatRepository._history_message(
            row,
            attachments.get(str(row["message_id"] or ""), ()),
        )

    @staticmethod
    def _turn_for_message(conn, turn_id: str) -> ChatAcceptedTurn:
        if not turn_id:
            return ChatAcceptedTurn(turn_id="", status=ChatTurnStatus.COMPLETED)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM chat_turn_jobs WHERE turn_id = %s",
                (turn_id,),
            )
            row = cursor.fetchone()
        status = ChatTurnStatus(str(row["status"])) if row else ChatTurnStatus.COMPLETED
        return ChatAcceptedTurn(turn_id=turn_id, status=status)

    @staticmethod
    def _history_message(row, attachments) -> ChatHistoryMessage:
        return ChatHistoryMessage(
            message_id=int(row["id"]),
            stable_message_id=str(row["message_id"] or ""),
            client_message_id=str(row["client_message_id"] or ""),
            role=str(row["role"]),
            message_type=str(row["message_type"]),
            content="" if row["message_type"] == "sticker" else str(row["content"]),
            content_parts=postgres_repositories._history_content_parts(attachments),
            sources=postgres_repositories._history_sources(attachments),
            created_at=row["created_at"],
            agent_turn_id=str(row["agent_turn_id"] or ""),
            reply_group_id=str(row["reply_group_id"] or ""),
            sequence_in_group=int(row["sequence_in_group"] or 0),
            in_reply_to_message_id=(
                int(row["in_reply_to_message_id"])
                if row["in_reply_to_message_id"] is not None
                else None
            ),
        )

    @staticmethod
    def _turn_job(row) -> ChatTurnJob:
        return ChatTurnJob(
            turn_id=str(row["turn_id"]),
            user_id=str(row["user_id"]),
            conversation_id=str(row["conversation_id"]),
            status=ChatTurnStatus(str(row["status"])),
            input_first_message_id=int(row["input_first_message_id"]),
            input_last_message_id=int(row["input_last_message_id"]),
            message_count=int(row["message_count"]),
            character_count=int(row["character_count"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            started_at=row["started_at"],
        )
