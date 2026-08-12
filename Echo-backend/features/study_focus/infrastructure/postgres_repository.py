from __future__ import annotations

from datetime import UTC, date, datetime

from db.postgres_connection import get_connection, transaction

from features.auth.public import ensure_user_identity
from features.study_focus.domain.entities import StudyFocusSession

_ACTIVE_STATUSES = {"running", "paused"}
_TERMINAL_STATUSES = {"completed", "ended_early"}
_ALL_STATUSES = _ACTIVE_STATUSES | _TERMINAL_STATUSES


class PostgresStudyFocusRepository:
    def create_session(
        self,
        *,
        user_id: str,
        session_id: str,
        activity_type: str,
        short_goal: str,
        planned_duration_seconds: int,
        started_at: datetime,
        timezone: str,
    ) -> StudyFocusSession:
        if not session_id.strip():
            raise ValueError("session_id is required")
        if planned_duration_seconds < 60 or planned_duration_seconds > 10800:
            raise ValueError("planned duration must be between 1 and 180 minutes")
        activity_type = activity_type.strip()[:40] or "学习"
        short_goal = short_goal.strip()[:80]
        timezone = timezone.strip()[:80] or "UTC"
        started_at = _as_utc(started_at)
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO study_focus_sessions (
                        session_id, user_id, activity_type, short_goal,
                        planned_duration_seconds, actual_duration_seconds,
                        status, started_at, timezone
                    ) VALUES (%s, %s, %s, %s, %s, 0, 'running', %s, %s)
                    ON CONFLICT (session_id) DO NOTHING
                    """,
                    (
                        session_id,
                        user_id,
                        activity_type,
                        short_goal,
                        planned_duration_seconds,
                        started_at,
                        timezone,
                    ),
                )
                cursor.execute(
                    "SELECT * FROM study_focus_sessions WHERE session_id = %s",
                    (session_id,),
                )
                row = cursor.fetchone()
        if row is None or str(row["user_id"]) != user_id:
            raise ValueError("study focus session is unavailable")
        return _session(row)

    def update_session(
        self,
        *,
        user_id: str,
        session_id: str,
        status: str,
        actual_duration_seconds: int,
        occurred_at: datetime,
    ) -> StudyFocusSession | None:
        if status not in _ALL_STATUSES:
            raise ValueError("invalid study focus status")
        occurred_at = _as_utc(occurred_at)
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                    SELECT * FROM study_focus_sessions
                    WHERE user_id = %s AND session_id = %s
                    FOR UPDATE
                    """,
                (user_id, session_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            current = str(row["status"])
            if current in _TERMINAL_STATUSES:
                return _session(row)
            if not _transition_allowed(current, status):
                raise ValueError(f"cannot change study focus status from {current} to {status}")
            planned = int(row["planned_duration_seconds"])
            actual = max(0, min(int(actual_duration_seconds), planned))
            ended_at = occurred_at if status in _TERMINAL_STATUSES else None
            cursor.execute(
                """
                    UPDATE study_focus_sessions
                    SET status = %s,
                        actual_duration_seconds = GREATEST(actual_duration_seconds, %s),
                        ended_at = COALESCE(%s, ended_at),
                        updated_at = NOW()
                    WHERE user_id = %s AND session_id = %s
                    RETURNING *
                    """,
                (status, actual, ended_at, user_id, session_id),
            )
            updated = cursor.fetchone()
        return _session(updated)

    def mark_completion_message(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: int,
    ) -> StudyFocusSession | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                    UPDATE study_focus_sessions
                    SET completion_message_id = COALESCE(completion_message_id, %s),
                        updated_at = NOW()
                    WHERE user_id = %s AND session_id = %s
                    RETURNING *
                    """,
                (message_id, user_id, session_id),
            )
            row = cursor.fetchone()
        return _session(row) if row else None

    def list_sessions(self, user_id: str, limit: int = 30) -> list[StudyFocusSession]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM study_focus_sessions
                WHERE user_id = %s
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (user_id, max(1, min(limit, 100))),
            )
            rows = cursor.fetchall()
        return [_session(row) for row in rows]

    def sessions_for_local_date(
        self,
        user_id: str,
        local_date: date,
        timezone_name: str,
    ) -> list[StudyFocusSession]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM study_focus_sessions
                WHERE user_id = %s
                  AND status IN ('completed', 'ended_early')
                  AND (COALESCE(ended_at, started_at) AT TIME ZONE %s)::date = %s
                ORDER BY started_at ASC
                """,
                (user_id, timezone_name, local_date),
            )
            rows = cursor.fetchall()
        return [_session(row) for row in rows]


def _transition_allowed(current: str, target: str) -> bool:
    if current == target:
        return True
    if current == "running":
        return target in {"paused", "completed", "ended_early"}
    if current == "paused":
        return target in {"running", "completed", "ended_early"}
    return False


def _session(row) -> StudyFocusSession:
    return StudyFocusSession(
        session_id=str(row["session_id"]),
        user_id=str(row["user_id"]),
        activity_type=str(row["activity_type"]),
        short_goal=str(row["short_goal"] or ""),
        planned_duration_seconds=int(row["planned_duration_seconds"]),
        actual_duration_seconds=int(row["actual_duration_seconds"] or 0),
        status=str(row["status"]),
        started_at=row["started_at"],
        timezone=str(row["timezone"] or "UTC"),
        ended_at=row["ended_at"],
        completion_message_id=(
            int(row["completion_message_id"])
            if row["completion_message_id"] is not None
            else None
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
