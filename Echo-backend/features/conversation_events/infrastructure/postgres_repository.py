from __future__ import annotations

import json

from db.postgres_connection import get_connection, transaction

from features.conversation_events.domain.entities import ConversationEvent


class PostgresConversationEventRepository:
    def append(self, event: ConversationEvent) -> int:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_events (
                    event_type, source, actor, user_id, conversation_id,
                    turn_id, content, payload, source_created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (
                    event.event_type,
                    event.source,
                    event.actor,
                    event.user_id,
                    event.conversation_id,
                    event.turn_id,
                    event.content[:8000],
                    json.dumps(event.payload, ensure_ascii=False),
                    event.source_created_at,
                ),
            )
            row = cursor.fetchone()
            return int(row["id"])

    def list_for_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int = 50,
    ) -> list[ConversationEvent]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, event_type, source, actor, user_id, conversation_id,
                       turn_id, content, payload, source_created_at, created_at
                FROM conversation_events
                WHERE user_id = %s AND conversation_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (user_id, conversation_id, max(1, limit)),
            )
            rows = cursor.fetchall()
        return [
            ConversationEvent(
                event_type=str(row["event_type"]),
                source=str(row["source"]),
                actor=str(row["actor"]),
                user_id=str(row["user_id"]),
                conversation_id=row["conversation_id"],
                turn_id=str(row["turn_id"] or ""),
                content=str(row["content"] or ""),
                payload=dict(row["payload"] or {}),
                source_created_at=row["source_created_at"],
            )
            for row in reversed(rows)
        ]
