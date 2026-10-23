import json
import uuid
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from db.postgres_connection import get_connection, transaction

from features.relationship.domain.entities import (
    RELATIONSHIP_SCHEMA_VERSION,
    RelationshipSignal,
    RelationshipState,
    default_relationship_state,
)
from features.relationship.domain.rules import calculate_relationship_score


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _state_from_row(row: dict[str, Any]) -> RelationshipState:
    return RelationshipState(
        user_id=str(row["user_id"]),
        stage=str(row["stage"]),
        relationship_mode=str(row.get("relationship_mode") or "friend"),
        score=int(row["score"]),
        interaction_turns=int(row["interaction_turns"]),
        active_days=int(row["active_days"]),
        shared_memory_count=int(row["shared_memory_count"]),
        positive_signal_count=int(row["positive_signal_count"]),
        explicit_relation_signal_count=int(row["explicit_relation_signal_count"]),
        boundary_signal_count=int(row["boundary_signal_count"]),
        affection_permission=str(row["affection_permission"]),
        last_interaction_date=_timestamp_text(row.get("last_interaction_date")),
        last_interaction_at=_timestamp_text(row.get("last_interaction_at")),
        last_boundary_at=_timestamp_text(row.get("last_boundary_at")),
        stage_updated_at=_timestamp_text(row.get("stage_updated_at")),
        created_at=_timestamp_text(row.get("created_at")),
        updated_at=_timestamp_text(row.get("updated_at")),
        schema_version=int(row.get("schema_version") or RELATIONSHIP_SCHEMA_VERSION),
    )


_STATE_COLUMNS = """
    user_id, stage, relationship_mode, score, interaction_turns, active_days,
    shared_memory_count, positive_signal_count, explicit_relation_signal_count,
    boundary_signal_count, affection_permission, last_interaction_date,
    last_interaction_at, last_boundary_at, stage_updated_at,
    created_at, updated_at, schema_version
"""


class PostgresRelationshipRepository:
    def _get(self, user_id: str) -> RelationshipState | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                f"SELECT {_STATE_COLUMNS} FROM relationship_states WHERE user_id = %s",
                (user_id,),
            )
            row = cursor.fetchone()
        return _state_from_row(row) if row else None

    def _build_historical_baseline(self, user_id: str) -> RelationshipState:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FILTER (WHERE role = 'user') AS interaction_turns,
                       COUNT(DISTINCT DATE(created_at)) FILTER (WHERE role = 'user') AS active_days,
                       MAX(created_at) FILTER (WHERE role = 'user') AS last_interaction_at,
                       MIN(created_at) FILTER (WHERE role = 'user') AS created_at
                FROM chat_messages
                WHERE user_id = %s AND status = 'active'
                """,
                (user_id,),
            )
            history = cursor.fetchone() or {}

        state = replace(
            default_relationship_state(user_id),
            interaction_turns=int(history.get("interaction_turns") or 0),
            active_days=int(history.get("active_days") or 0),
            shared_memory_count=self.count_active_memories(user_id),
            last_interaction_date=_timestamp_text(history.get("last_interaction_at"))[:10]
            if history.get("last_interaction_at")
            else None,
            last_interaction_at=_timestamp_text(history.get("last_interaction_at")),
            created_at=_timestamp_text(history.get("created_at")),
        )
        return replace(state, score=calculate_relationship_score(state))

    def get_or_create(self, user_id: str) -> RelationshipState:
        existing = self._get(user_id)
        if existing:
            return existing

        baseline = self._build_historical_baseline(user_id)
        self.save_progress(baseline, (), None)
        return self._get(user_id) or baseline

    def count_active_memories(self, user_id: str) -> int:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM user_memories WHERE user_id = %s AND status = 'active'",
                (user_id,),
            )
            row = cursor.fetchone()
        return int(row["count"] if row else 0)

    def save_progress(
        self,
        state: RelationshipState,
        signals: tuple[RelationshipSignal, ...],
        source_message_id: int | None,
    ) -> RelationshipState:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO relationship_states (
                    user_id, stage, relationship_mode, score, interaction_turns, active_days,
                    shared_memory_count, positive_signal_count, explicit_relation_signal_count,
                    boundary_signal_count, affection_permission, last_interaction_date,
                    last_interaction_at, last_boundary_at, stage_updated_at,
                    created_at, updated_at, schema_version
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()), %s
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    score = EXCLUDED.score,
                    interaction_turns = EXCLUDED.interaction_turns,
                    active_days = EXCLUDED.active_days,
                    shared_memory_count = EXCLUDED.shared_memory_count,
                    positive_signal_count = EXCLUDED.positive_signal_count,
                    explicit_relation_signal_count = EXCLUDED.explicit_relation_signal_count,
                    boundary_signal_count = EXCLUDED.boundary_signal_count,
                    affection_permission = EXCLUDED.affection_permission,
                    last_interaction_date = EXCLUDED.last_interaction_date,
                    last_interaction_at = EXCLUDED.last_interaction_at,
                    last_boundary_at = EXCLUDED.last_boundary_at,
                    stage_updated_at = EXCLUDED.stage_updated_at,
                    updated_at = EXCLUDED.updated_at,
                    schema_version = EXCLUDED.schema_version
                RETURNING {_STATE_COLUMNS}
                """,
                (
                    state.user_id,
                    state.stage,
                    state.relationship_mode,
                    state.score,
                    state.interaction_turns,
                    state.active_days,
                    state.shared_memory_count,
                    state.positive_signal_count,
                    state.explicit_relation_signal_count,
                    state.boundary_signal_count,
                    state.affection_permission,
                    state.last_interaction_date,
                    state.last_interaction_at,
                    state.last_boundary_at,
                    state.stage_updated_at,
                    state.created_at,
                    state.updated_at,
                    state.schema_version,
                ),
            )
            row = cursor.fetchone()

            for signal in signals:
                metadata = {"stage": state.stage} if signal.event_type == "stage_changed" else {}
                cursor.execute(
                    """
                    INSERT INTO relationship_events (
                        event_id, user_id, event_type, weight, source_message_id, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        f"rel_evt_{uuid.uuid4().hex}",
                        state.user_id,
                        signal.event_type,
                        signal.weight,
                        source_message_id,
                        json.dumps(metadata),
                    ),
                )
        if not row:
            raise RuntimeError("Relationship state upsert returned no row")
        return _state_from_row(row)

    def update_mode(self, user_id: str, relationship_mode: str) -> RelationshipState:
        with transaction() as conn, conn.cursor() as cursor:
            # Progress saves deliberately do not update this column, so a concurrent
            # completed turn cannot overwrite the user's explicit choice.
            cursor.execute(
                f"""
                UPDATE relationship_states
                SET relationship_mode = %s, schema_version = %s, updated_at = NOW()
                WHERE user_id = %s
                RETURNING {_STATE_COLUMNS}
                """,
                (relationship_mode, RELATIONSHIP_SCHEMA_VERSION, user_id),
            )
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("Relationship mode update returned no row")
        return _state_from_row(row)

    def reset(self, user_id: str) -> RelationshipState:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute("DELETE FROM relationship_events WHERE user_id = %s", (user_id,))
            cursor.execute(
                f"""
                UPDATE relationship_states SET
                    stage = 'new', score = 0, interaction_turns = 0, active_days = 0,
                    shared_memory_count = 0, positive_signal_count = 0,
                    explicit_relation_signal_count = 0, boundary_signal_count = 0,
                    affection_permission = 'unknown', last_interaction_date = NULL,
                    last_interaction_at = NULL, last_boundary_at = NULL,
                    stage_updated_at = NULL, created_at = NOW(), updated_at = NOW(),
                    schema_version = %s
                WHERE user_id = %s
                RETURNING {_STATE_COLUMNS}
                """,
                (RELATIONSHIP_SCHEMA_VERSION, user_id),
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    f"""
                    INSERT INTO relationship_states (user_id, schema_version)
                    VALUES (%s, %s)
                    RETURNING {_STATE_COLUMNS}
                    """,
                    (user_id, RELATIONSHIP_SCHEMA_VERSION),
                )
                row = cursor.fetchone()
        if not row:
            raise RuntimeError("Relationship state reset returned no row")
        return _state_from_row(row)
