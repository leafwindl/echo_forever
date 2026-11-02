from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from db.postgres_connection import get_connection, transaction
from psycopg.types.json import Jsonb

from features.presence.domain.entities import PresenceState, PresenceThought


def _state(row: dict[str, Any]) -> PresenceState:
    return PresenceState(
        user_id=str(row["user_id"]),
        status=str(row["status"]),
        enabled=bool(row["enabled"]),
        last_user_message_at=row.get("last_user_message_at"),
        last_tick_at=row.get("last_tick_at"),
        last_thought_at=row.get("last_thought_at"),
        thought_budget_date=row.get("thought_budget_date"),
        thoughts_used=int(row.get("thoughts_used") or 0),
        last_decision=str(row.get("last_decision") or ""),
        last_decision_reason=str(row.get("last_decision_reason") or ""),
    )


def _thought(row: dict[str, Any]) -> PresenceThought:
    return PresenceThought(
        thought_id=str(row["thought_id"]),
        user_id=str(row["user_id"]),
        text=str(row["text"]),
        salience=float(row["salience"]),
        shareable=bool(row["shareable"]),
        action_intent=str(row["action_intent"] or ""),
        source_memory_id=str(row["source_memory_id"] or ""),
        source_memory_text=str(row["source_memory_text"] or ""),
        created_at=row.get("created_at"),
    )


class PostgresPresenceRepository:
    def get_or_create_state(self, user_id: str) -> PresenceState:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO presence_states (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,),
            )
            cursor.execute("SELECT * FROM presence_states WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Presence state could not be created")
        return _state(row)

    def save_state(self, state: PresenceState) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE presence_states
                SET status = %s, enabled = %s, last_user_message_at = %s,
                    last_tick_at = %s, last_thought_at = %s,
                    thought_budget_date = %s, thoughts_used = %s,
                    last_decision = %s, last_decision_reason = %s,
                    updated_at = NOW()
                WHERE user_id = %s
                """,
                (
                    state.status,
                    state.enabled,
                    state.last_user_message_at,
                    state.last_tick_at,
                    state.last_thought_at,
                    state.thought_budget_date,
                    state.thoughts_used,
                    state.last_decision,
                    state.last_decision_reason,
                    state.user_id,
                ),
            )

    def recent_thoughts(self, user_id: str, limit: int) -> list[PresenceThought]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM presence_thoughts
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_thought(row) for row in cursor.fetchall()]

    def add_thought(self, thought: PresenceThought) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO presence_thoughts (
                    thought_id, user_id, text, salience, shareable,
                    action_intent, source_memory_id, source_memory_text, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
                """,
                (
                    thought.thought_id,
                    thought.user_id,
                    thought.text,
                    thought.salience,
                    thought.shareable,
                    thought.action_intent,
                    thought.source_memory_id,
                    thought.source_memory_text,
                    thought.created_at,
                ),
            )

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        detail: dict,
        now: datetime,
    ) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO presence_events (event_id, user_id, event_type, detail, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    f"pevent_{uuid.uuid4().hex}",
                    user_id,
                    event_type,
                    Jsonb(detail),
                    now,
                ),
            )
