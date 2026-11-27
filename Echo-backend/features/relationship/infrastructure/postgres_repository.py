import json
import uuid
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from db.postgres_connection import get_connection, transaction

from features.relationship.domain.entities import (
    RELATIONSHIP_SCHEMA_VERSION,
    RELATIONSHIP_STAGES,
    RelationshipSignal,
    RelationshipState,
    RelationshipValidationError,
    StageAdvanceRequest,
    default_relationship_state,
)
from features.relationship.domain.affection import (
    cap_daily_delta,
    clamp_affection,
)
from features.relationship.domain.rules import normalize_relationship_stage


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _state_from_row(row: dict[str, Any]) -> RelationshipState:
    return RelationshipState(
        user_id=str(row["user_id"]),
        stage=normalize_relationship_stage(str(row["stage"])),
        reset_epoch=int(row.get("reset_epoch") or 0),
        affection=int(row.get("affection") or 1),
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
    user_id, stage,
    reset_epoch, affection, interaction_turns, active_days,
    shared_memory_count, positive_signal_count, explicit_relation_signal_count,
    boundary_signal_count, affection_permission, last_interaction_date,
    last_interaction_at, last_boundary_at, stage_updated_at,
    created_at, updated_at, schema_version
"""

def _stage_request_from_row(row: dict[str, Any]) -> StageAdvanceRequest:
    return StageAdvanceRequest(
        request_id=str(row["request_id"]),
        user_id=str(row["user_id"]),
        target_stage=str(row["target_stage"]),
        status=str(row["status"]),
        conversation_id=str(row["conversation_id"]) if row.get("conversation_id") else None,
        agent_turn_id=str(row["agent_turn_id"]) if row.get("agent_turn_id") else None,
        evidence=str(row.get("evidence") or ""),
        created_at=_timestamp_text(row.get("created_at")),
        resolved_at=_timestamp_text(row.get("resolved_at")),
        expires_at=_timestamp_text(row.get("expires_at")),
        cooldown_until=_timestamp_text(row.get("cooldown_until")),
    )


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
        return state

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
                    user_id, stage,
                    reset_epoch, affection, interaction_turns, active_days,
                    shared_memory_count, positive_signal_count, explicit_relation_signal_count,
                    boundary_signal_count, affection_permission, last_interaction_date,
                    last_interaction_at, last_boundary_at, stage_updated_at,
                    created_at, updated_at, schema_version
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()), %s
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    affection = EXCLUDED.affection,
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
                    state.reset_epoch,
                    state.affection,
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

    def adjust_affection(
        self,
        *,
        user_id: str,
        delta: int,
        reason: str,
        agent_turn_id: str,
        observed_at: datetime | None = None,
    ) -> tuple[RelationshipState, int]:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise RelationshipValidationError("Missing user_id")
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO relationship_states (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (clean_user_id,),
            )
            cursor.execute(
                f"""
                SELECT {_STATE_COLUMNS}
                FROM relationship_states
                WHERE user_id = %s
                FOR UPDATE
                """,
                (clean_user_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Relationship state lock returned no row")
            state = _state_from_row(row)

            if agent_turn_id.strip():
                cursor.execute(
                    """
                    SELECT 1
                    FROM relationship_events
                    WHERE user_id = %s
                      AND event_type = 'affection_delta'
                      AND metadata->>'agent_turn_id' = %s
                    LIMIT 1
                    """,
                    (clean_user_id, agent_turn_id.strip()),
                )
                if cursor.fetchone():
                    return state, 0

            cursor.execute(
                """
                SELECT COALESCE(SUM(weight), 0) AS total
                FROM relationship_events
                WHERE user_id = %s
                  AND event_type = 'affection_delta'
                  AND created_at >= date_trunc('day', NOW())
                """,
                (clean_user_id,),
            )
            daily_row = cursor.fetchone() or {}
            daily_net = int(daily_row.get("total") or 0)
            allowed = cap_daily_delta(delta, daily_net)
            if allowed == 0:
                return state, 0

            before = state.affection
            after = clamp_affection(before + allowed)
            applied = after - before
            if applied == 0:
                return state, 0
            new_stage = state.stage
            stage_updated_at = state.stage_updated_at
            if state.stage == "new" and after >= 100:
                new_stage = "familiar"
                stage_updated_at = (
                    observed_at.isoformat() if observed_at is not None else datetime.now().isoformat()
                )
            cursor.execute(
                f"""
                UPDATE relationship_states
                SET affection = %s,
                    stage = %s,
                    affection_updated_at = NOW(),
                    stage_updated_at = %s,
                    updated_at = NOW()
                WHERE user_id = %s
                RETURNING {_STATE_COLUMNS}
                """,
                (after, new_stage, stage_updated_at, clean_user_id),
            )
            updated_row = cursor.fetchone()
            if not updated_row:
                raise RuntimeError("Relationship affection update returned no row")
            cursor.execute(
                """
                INSERT INTO relationship_events (
                    event_id, user_id, event_type, weight, source_message_id, metadata
                )
                VALUES (%s, %s, 'affection_delta', %s, NULL, %s::jsonb)
                """,
                (
                    f"rel_evt_{uuid.uuid4().hex}",
                    clean_user_id,
                    applied,
                    json.dumps(
                        {
                            "reason": reason,
                            "before": before,
                            "after": after,
                            "agent_turn_id": agent_turn_id.strip(),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            return _state_from_row(updated_row), applied

    def create_stage_request(
        self,
        *,
        user_id: str,
        target_stage: str,
        conversation_id: str | None,
        agent_turn_id: str | None,
        evidence: str,
        expires_at: str,
    ) -> StageAdvanceRequest:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO relationship_stage_requests (
                    request_id, user_id, target_stage, status, conversation_id,
                    agent_turn_id, evidence, expires_at
                )
                VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s::timestamptz)
                RETURNING *
                """,
                (
                    f"rel_stage_{uuid.uuid4().hex}",
                    user_id,
                    target_stage,
                    conversation_id,
                    agent_turn_id,
                    evidence[:300],
                    expires_at,
                ),
            )
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("Relationship stage request insert returned no row")
        return _stage_request_from_row(row)

    def get_pending_stage_request(self, user_id: str) -> StageAdvanceRequest | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM relationship_stage_requests
                WHERE user_id = %s AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return _stage_request_from_row(row) if row else None

    def get_stage_request(self, user_id: str, request_id: str) -> StageAdvanceRequest | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM relationship_stage_requests
                WHERE user_id = %s AND request_id = %s
                """,
                (user_id, request_id),
            )
            row = cursor.fetchone()
        return _stage_request_from_row(row) if row else None

    def latest_stage_request(self, user_id: str) -> StageAdvanceRequest | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM relationship_stage_requests
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return _stage_request_from_row(row) if row else None

    def accept_stage_request(
        self,
        *,
        user_id: str,
        request_id: str,
        resolved_at: str,
    ) -> RelationshipState:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM relationship_stage_requests
                WHERE user_id = %s AND request_id = %s
                FOR UPDATE
                """,
                (user_id, request_id),
            )
            request_row = cursor.fetchone()
            if not request_row or request_row["status"] != "pending":
                raise RelationshipValidationError("No pending stage request")
            cursor.execute(
                f"""
                SELECT {_STATE_COLUMNS}
                FROM relationship_states
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            )
            state_row = cursor.fetchone()
            if not state_row:
                raise RelationshipValidationError("Relationship state missing")
            current_stage = normalize_relationship_stage(str(state_row["stage"]))
            target_stage = str(request_row["target_stage"])
            if RELATIONSHIP_STAGES.index(target_stage) <= RELATIONSHIP_STAGES.index(current_stage):
                raise RelationshipValidationError("Stage request target is not ahead")
            cursor.execute(
                f"""
                UPDATE relationship_states
                SET stage = %s,
                    stage_updated_at = %s::timestamptz,
                    updated_at = NOW()
                WHERE user_id = %s
                RETURNING {_STATE_COLUMNS}
                """,
                (target_stage, resolved_at, user_id),
            )
            updated_state = cursor.fetchone()
            cursor.execute(
                """
                UPDATE relationship_stage_requests
                SET status = 'accepted', resolved_at = %s::timestamptz
                WHERE user_id = %s AND request_id = %s AND status = 'pending'
                """,
                (resolved_at, user_id, request_id),
            )
        if not updated_state:
            raise RuntimeError("Relationship stage update returned no row")
        return _state_from_row(updated_state)

    def resolve_stage_request(
        self,
        *,
        user_id: str,
        request_id: str,
        status: str,
        resolved_at: str,
        cooldown_until: str | None,
    ) -> StageAdvanceRequest:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE relationship_stage_requests
                SET status = %s,
                    resolved_at = %s::timestamptz,
                    cooldown_until = %s::timestamptz
                WHERE user_id = %s AND request_id = %s AND status = 'pending'
                RETURNING *
                """,
                (status, resolved_at, cooldown_until, user_id, request_id),
            )
            row = cursor.fetchone()
        if not row:
            raise RelationshipValidationError("No pending stage request")
        return _stage_request_from_row(row)

    def reset(self, user_id: str) -> RelationshipState:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute("DELETE FROM relationship_events WHERE user_id = %s", (user_id,))
            cursor.execute(
                f"""
                UPDATE relationship_states SET
                    stage = 'new', reset_epoch = reset_epoch + 1,
                    affection = 1, interaction_turns = 0, active_days = 0,
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
