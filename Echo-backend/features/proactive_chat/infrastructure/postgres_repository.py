from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from db.postgres_connection import get_connection, transaction

from features.agent.domain.entities import ContentPart
from features.auth.public import ensure_user_identity
from features.chat.infrastructure import postgres_repositories
from features.proactive_chat.domain.entities import (
    ChatSchedule,
    ProactiveChatJob,
    ProactiveChatPreferences,
)

# The quota window starts at the first delivery and rolls forward; it is not a calendar-day quota.
_LEVEL_LIMITS = {
    "conservative": (timedelta(hours=24), 4, timedelta(days=7)),
    "balanced": (timedelta(hours=6), 4, timedelta(days=1)),
    "active": (timedelta(hours=2), 6, timedelta(days=1)),
}


def _timezone(value: str) -> str:
    clean = value.strip() or "Asia/Shanghai"
    try:
        ZoneInfo(clean)
    except Exception as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return clean


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("local_datetime must include a timezone offset")
    return value.astimezone(UTC)


def _preference(row) -> ProactiveChatPreferences:
    return ProactiveChatPreferences(
        user_id=str(row["user_id"]),
        enabled=bool(row["enabled"]),
        allow_echo_scheduling=bool(row["allow_echo_scheduling"]),
        allow_spontaneous_chat=bool(row["allow_spontaneous_chat"]),
        proactivity_level=str(row["proactivity_level"]),
        timezone=str(row["timezone"]),
        quiet_start=row["quiet_start"],
        quiet_end=row["quiet_end"],
        explicit_reminder_quiet_policy=str(row["explicit_reminder_quiet_policy"]),
        notification_preview=bool(row["notification_preview"]),
        proactive_count=int(row["proactive_count"]),
        window_started_at=row["window_started_at"],
        last_proactive_at=row["last_proactive_at"],
        consecutive_unanswered=int(row["consecutive_unanswered"]),
    )


def _schedule(row) -> ChatSchedule:
    rule = row["recurrence_rule"] or {}
    if isinstance(rule, str):
        rule = json.loads(rule)
    return ChatSchedule(
        schedule_id=str(row["schedule_id"]),
        user_id=str(row["user_id"]),
        conversation_id=str(row["conversation_id"]) if row["conversation_id"] else None,
        created_by=str(row["created_by"]),
        schedule_type=str(row["schedule_type"]),
        intent=str(row["intent"]),
        user_visible_label=str(row["user_visible_label"] or ""),
        timezone=str(row["timezone"]),
        next_run_at=row["next_run_at"],
        recurrence_rule=dict(rule),
        status=str(row["status"]),
        run_count=int(row["run_count"]),
        max_runs=int(row["max_runs"]) if row["max_runs"] is not None else None,
        last_run_at=row["last_run_at"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class PostgresProactiveChatRepository:
    def get_preferences(self, user_id: str) -> ProactiveChatPreferences:
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO proactive_chat_preferences (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id,),
                )
                cursor.execute(
                    "SELECT * FROM proactive_chat_preferences WHERE user_id = %s",
                    (user_id,),
                )
                row = cursor.fetchone()
        return _preference(row)

    def save_preferences(
        self,
        user_id: str,
        *,
        enabled: bool,
        allow_echo_scheduling: bool,
        allow_spontaneous_chat: bool,
        proactivity_level: str,
        timezone: str,
        quiet_start: time,
        quiet_end: time,
        explicit_reminder_quiet_policy: str,
        notification_preview: bool,
    ) -> ProactiveChatPreferences:
        level = proactivity_level.strip().lower()
        if level not in _LEVEL_LIMITS:
            raise ValueError("proactivity_level must be conservative, balanced, or active")
        policy = explicit_reminder_quiet_policy.strip().lower()
        if policy not in {"honor", "defer"}:
            raise ValueError("explicit_reminder_quiet_policy must be honor or defer")
        timezone = _timezone(timezone)
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO proactive_chat_preferences (
                        user_id, enabled, allow_echo_scheduling,
                        allow_spontaneous_chat, proactivity_level, timezone,
                        quiet_start, quiet_end, explicit_reminder_quiet_policy,
                        notification_preview
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        allow_echo_scheduling = EXCLUDED.allow_echo_scheduling,
                        allow_spontaneous_chat = EXCLUDED.allow_spontaneous_chat,
                        proactivity_level = EXCLUDED.proactivity_level,
                        timezone = EXCLUDED.timezone,
                        quiet_start = EXCLUDED.quiet_start,
                        quiet_end = EXCLUDED.quiet_end,
                        explicit_reminder_quiet_policy = EXCLUDED.explicit_reminder_quiet_policy,
                        notification_preview = EXCLUDED.notification_preview,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        user_id,
                        enabled,
                        allow_echo_scheduling,
                        allow_spontaneous_chat,
                        level,
                        timezone,
                        quiet_start,
                        quiet_end,
                        policy,
                        notification_preview,
                    ),
                )
                row = cursor.fetchone()
        return _preference(row)

    def list_schedules(self, user_id: str) -> tuple[ChatSchedule, ...]:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM chat_schedules schedule
                WHERE schedule.user_id = %s
                  AND (
                    schedule.status IN ('cancelled', 'completed')
                    OR (
                      schedule.schedule_type = 'once'
                      AND schedule.next_run_at < NOW() - CASE
                        WHEN schedule.created_by = 'user_request'
                          THEN INTERVAL '30 minutes'
                        ELSE INTERVAL '60 minutes'
                      END
                      AND NOT EXISTS (
                        SELECT 1
                        FROM proactive_chat_jobs job
                        WHERE job.schedule_id = schedule.schedule_id
                          AND job.status IN ('pending', 'retry_wait', 'running')
                      )
                    )
                  )
                """,
                (user_id,),
            )
            cursor.execute(
                """
                SELECT * FROM chat_schedules
                WHERE user_id = %s AND status IN ('active', 'paused')
                ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,
                         next_run_at ASC, id ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return tuple(_schedule(row) for row in rows)

    def get_schedule(self, user_id: str, schedule_id: str) -> ChatSchedule | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM chat_schedules WHERE user_id = %s AND schedule_id = %s",
                (user_id, schedule_id),
            )
            row = cursor.fetchone()
        return _schedule(row) if row else None

    def create_schedule(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        created_by: str,
        schedule_type: str,
        intent: str,
        user_visible_label: str,
        local_datetime: datetime,
        timezone: str,
        recurrence_rule: dict[str, object] | None = None,
    ) -> ChatSchedule:
        clean_intent = intent.strip()
        if not clean_intent:
            raise ValueError("intent is required")
        kind = schedule_type.strip().lower()
        if kind not in {"once", "daily", "weekly"}:
            raise ValueError("schedule_type must be once, daily, or weekly")
        if created_by not in {"user_request", "echo_agent", "system_policy"}:
            raise ValueError("invalid schedule creator")
        zone = _timezone(timezone)
        next_run_at = _as_utc(local_datetime)
        if next_run_at <= datetime.now(UTC):
            raise ValueError("schedule time must be in the future")
        schedule_id = f"schedule_{uuid.uuid4().hex}"
        max_runs = 1 if kind == "once" else None
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO chat_schedules (
                        schedule_id, user_id, conversation_id, created_by, schedule_type,
                        intent, user_visible_label, timezone, next_run_at, recurrence_rule,
                        max_runs
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING *
                    """,
                    (
                        schedule_id,
                        user_id,
                        conversation_id,
                        created_by,
                        kind,
                        clean_intent,
                        user_visible_label.strip(),
                        zone,
                        next_run_at,
                        json.dumps(recurrence_rule or {}, ensure_ascii=False),
                        max_runs,
                    ),
                )
                row = cursor.fetchone()
                self._insert_job(cursor, schedule_id, user_id, conversation_id, next_run_at)
        return _schedule(row)

    def update_schedule(
        self,
        user_id: str,
        schedule_id: str,
        *,
        status: str | None = None,
        user_visible_label: str | None = None,
        local_datetime: datetime | None = None,
        timezone: str | None = None,
    ) -> ChatSchedule | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM chat_schedules WHERE user_id = %s AND schedule_id = %s FOR UPDATE",
                (user_id, schedule_id),
            )
            current = cursor.fetchone()
            if current is None:
                return None
            next_status = status.strip().lower() if status is not None else str(current["status"])
            if next_status not in {"active", "paused", "cancelled"}:
                raise ValueError("status must be active, paused, or cancelled")
            next_timezone = (
                _timezone(timezone) if timezone is not None else str(current["timezone"])
            )
            next_run_at = (
                _as_utc(local_datetime) if local_datetime is not None else current["next_run_at"]
            )
            if local_datetime is not None and next_run_at <= datetime.now(UTC):
                raise ValueError("schedule time must be in the future")
            label = (
                user_visible_label.strip()
                if user_visible_label is not None
                else str(current["user_visible_label"] or "")
            )
            cursor.execute(
                """
                    UPDATE chat_schedules
                    SET status = %s, user_visible_label = %s, timezone = %s,
                        next_run_at = %s, updated_at = NOW()
                    WHERE schedule_id = %s
                    RETURNING *
                    """,
                (next_status, label, next_timezone, next_run_at, schedule_id),
            )
            row = cursor.fetchone()
            if next_status != "active":
                cursor.execute(
                    """
                        UPDATE proactive_chat_jobs
                        SET status = 'suppressed', updated_at = NOW()
                        WHERE schedule_id = %s AND status IN ('pending', 'retry_wait')
                        """,
                    (schedule_id,),
                )
            elif local_datetime is not None or str(current["status"]) != "active":
                if local_datetime is not None:
                    cursor.execute(
                        """
                            UPDATE proactive_chat_jobs
                            SET status = 'suppressed', updated_at = NOW()
                            WHERE schedule_id = %s AND status IN ('pending', 'retry_wait')
                            """,
                        (schedule_id,),
                    )
                self._insert_job(
                    cursor,
                    schedule_id,
                    user_id,
                    str(current["conversation_id"]) if current["conversation_id"] else None,
                    next_run_at,
                )
        return _schedule(row)

    def delete_schedule(self, user_id: str, schedule_id: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT schedule_id FROM chat_schedules
                WHERE user_id = %s AND schedule_id = %s
                FOR UPDATE
                """,
                (user_id, schedule_id),
            )
            if cursor.fetchone() is None:
                return False
            cursor.execute(
                """
                UPDATE proactive_chat_jobs
                SET status = 'suppressed', error_code = 'schedule_deleted',
                    lease_expires_at = NULL, updated_at = NOW()
                WHERE schedule_id = %s
                  AND status IN ('pending', 'retry_wait', 'running')
                """,
                (schedule_id,),
            )
            cursor.execute(
                "DELETE FROM chat_schedules WHERE user_id = %s AND schedule_id = %s",
                (user_id, schedule_id),
            )
        return True

    def claim_due_job(self, lease_seconds: int) -> ProactiveChatJob | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                    UPDATE proactive_chat_jobs
                    SET status = CASE
                            WHEN attempt_count < max_attempts THEN 'retry_wait'
                            ELSE 'failed'
                        END,
                        error_code = CASE
                            WHEN attempt_count < max_attempts THEN 'worker_lease_expired'
                            ELSE 'worker_lease_exhausted'
                        END,
                        scheduled_for = CASE
                            WHEN attempt_count < max_attempts THEN NOW()
                            ELSE scheduled_for
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
                    SELECT * FROM proactive_chat_jobs
                    WHERE status IN ('pending', 'retry_wait')
                      AND scheduled_for <= NOW()
                      AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
                    ORDER BY scheduled_for ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                    UPDATE proactive_chat_jobs
                    SET status = 'running', attempt_count = attempt_count + 1,
                        lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                (lease_seconds, row["job_id"]),
            )
            claimed = cursor.fetchone()
        return ProactiveChatJob(
            job_id=str(claimed["job_id"]),
            schedule_id=str(claimed["schedule_id"]) if claimed["schedule_id"] else None,
            user_id=str(claimed["user_id"]),
            conversation_id=str(claimed["conversation_id"]) if claimed["conversation_id"] else None,
            scheduled_for=claimed["scheduled_for"],
            status=str(claimed["status"]),
            attempt_count=int(claimed["attempt_count"]),
            max_attempts=int(claimed["max_attempts"]),
        )

    def create_spontaneous_job_if_due(self) -> bool:
        now = datetime.now(UTC)
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                    SELECT pref.*,
                           (
                             SELECT MAX(message.created_at)
                             FROM chat_messages message
                             WHERE message.user_id = pref.user_id
                               AND message.role = 'user'
                               AND message.status = 'active'
                           ) AS last_user_at
                    FROM proactive_chat_preferences pref
                    WHERE pref.enabled = TRUE
                      AND pref.allow_spontaneous_chat = TRUE
                      AND pref.consecutive_unanswered < 2
                      AND NOT EXISTS (
                          SELECT 1 FROM proactive_chat_jobs job
                          WHERE job.user_id = pref.user_id
                            AND job.schedule_id IS NULL
                            AND job.status IN ('pending', 'retry_wait', 'running')
                      )
                    ORDER BY pref.last_proactive_at NULLS FIRST, pref.updated_at ASC
                    LIMIT 40
                    FOR UPDATE SKIP LOCKED
                    """
            )
            rows = cursor.fetchall()
            for row in rows:
                last_user_at = row["last_user_at"]
                if last_user_at is None or not self._spontaneous_allowed(
                    _preference(row), last_user_at, now
                ):
                    continue
                conversation_id = postgres_repositories.get_or_create_active_conversation(
                    str(row["user_id"]), conn=conn
                )
                self._insert_job(cursor, None, str(row["user_id"]), conversation_id, now)
                return True
        return False

    def load_job_context(
        self,
        job: ProactiveChatJob,
    ) -> tuple[ProactiveChatPreferences, ChatSchedule | None, str]:
        preference = self.get_preferences(job.user_id)
        schedule = self.get_schedule(job.user_id, job.schedule_id) if job.schedule_id else None
        conversation_id = (
            job.conversation_id
            or postgres_repositories.get_or_create_active_conversation(job.user_id)
        )
        return preference, schedule, conversation_id

    def suppress_job(self, job_id: str, reason: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE proactive_chat_jobs
                SET status = 'suppressed', error_code = %s, lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (reason[:120], job_id),
            )

    def defer_job_to(self, job_id: str, run_at: datetime, reason: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE proactive_chat_jobs
                SET status = 'pending', scheduled_for = %s, error_code = %s,
                    lease_expires_at = NULL, updated_at = NOW()
                WHERE job_id = %s
                """,
                (run_at, reason[:120], job_id),
            )

    def fail_job(self, job: ProactiveChatJob, error_code: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            if job.attempt_count >= job.max_attempts:
                cursor.execute(
                    """
                    UPDATE proactive_chat_jobs
                    SET status = 'failed', error_code = %s, lease_expires_at = NULL,
                        updated_at = NOW()
                    WHERE job_id = %s
                    """,
                    (error_code[:120], job.job_id),
                )
                if job.schedule_id:
                    cursor.execute(
                        """
                        DELETE FROM chat_schedules
                        WHERE schedule_id = %s AND schedule_type = 'once'
                        """,
                        (job.schedule_id,),
                    )
            else:
                cursor.execute(
                    """
                    UPDATE proactive_chat_jobs
                    SET status = 'retry_wait', scheduled_for = NOW() + INTERVAL '30 seconds',
                        error_code = %s, lease_expires_at = NULL, updated_at = NOW()
                    WHERE job_id = %s
                    """,
                    (error_code[:120], job.job_id),
                )

    def persist_delivery(
        self,
        *,
        job: ProactiveChatJob,
        preference: ProactiveChatPreferences,
        schedule: ChatSchedule | None,
        conversation_id: str,
        reply_segments: tuple[str, ...],
        content_parts: tuple[ContentPart, ...],
        sticker_placement: str,
        agent_turn_id: str,
    ) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        group_id = f"proactive_{job.job_id}"
        messages: list[dict[str, object]] = []
        sequence = 0
        with transaction() as conn:
            ensure_user_identity(user_id=job.user_id, conn=conn)
            cursor = conn.cursor()
            if schedule is not None:
                cursor.execute(
                    """
                    SELECT status FROM chat_schedules
                    WHERE user_id = %s AND schedule_id = %s
                    FOR UPDATE
                    """,
                    (job.user_id, schedule.schedule_id),
                )
                current_schedule = cursor.fetchone()
                if current_schedule is None or str(current_schedule["status"]) != "active":
                    cursor.execute(
                        """
                        UPDATE proactive_chat_jobs
                        SET status = 'suppressed', error_code = 'schedule_inactive',
                            lease_expires_at = NULL, updated_at = NOW()
                        WHERE job_id = %s
                        """,
                        (job.job_id,),
                    )
                    return []

            def insert_message(
                content: str, message_type: str, parts: tuple[ContentPart, ...]
            ) -> None:
                nonlocal sequence
                message_id, stable_id = postgres_repositories._add_message_record(
                    user_id=job.user_id,
                    role="assistant",
                    content=content,
                    conversation_id=conversation_id,
                    message_type=message_type,
                    conn=conn,
                    agent_turn_id=agent_turn_id or job.job_id,
                    reply_group_id=group_id,
                    sequence_in_group=sequence,
                )
                postgres_repositories._add_message_attachments(
                    conn, job.user_id, stable_id, parts, 0 if not content else 1
                )
                messages.append(
                    {
                        "message_id": message_id,
                        "stable_message_id": stable_id,
                        "client_message_id": "",
                        "role": "assistant",
                        "message_type": message_type,
                        "content": content,
                        "content_parts": [
                            {
                                "type": part.type,
                                "text": part.text,
                                "sticker_id": part.sticker_id,
                                "url": part.url,
                            }
                            for part in parts
                        ],
                        "sources": [],
                        "agent_turn_id": agent_turn_id or job.job_id,
                        "reply_group_id": group_id,
                        "sequence_in_group": sequence,
                        "in_reply_to_message_id": None,
                        "created_at": now.isoformat(),
                    }
                )
                sequence += 1

            stickers = tuple(part for part in content_parts if part.type == "sticker")
            if stickers and sticker_placement == "before_text":
                insert_message("", "sticker", stickers)
            for segment in reply_segments:
                if segment.strip():
                    insert_message(segment.strip(), "text", ())
            if stickers and sticker_placement != "before_text":
                insert_message("", "sticker", stickers)
            if not messages:
                insert_message("", "text", ())

            first_message_id = str(messages[0]["stable_message_id"])
            body = "\n".join(reply_segments).strip() if preference.notification_preview else ""
            notification_id = f"notification_{uuid.uuid4().hex}"
            cursor.execute(
                """
                INSERT INTO notification_outbox (
                    notification_id, user_id, message_id, notification_type,
                    body_policy, body, payload
                ) VALUES (%s, %s, %s, 'proactive_message', %s, %s, %s::jsonb)
                """,
                (
                    notification_id,
                    job.user_id,
                    first_message_id,
                    "preview" if preference.notification_preview else "hidden",
                    body[:240],
                    json.dumps(
                        {
                            "schema_version": "1",
                            "type": "proactive_message",
                            "route": "chat",
                            "notification_id": notification_id,
                            "entity_id": first_message_id,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            cursor.execute(
                """
                UPDATE proactive_chat_jobs
                SET status = 'succeeded', message_id = %s, lease_expires_at = NULL,
                    error_code = NULL, updated_at = NOW()
                WHERE job_id = %s
                """,
                (first_message_id, job.job_id),
            )
            self._mark_preference_delivery(cursor, preference, now)
            if schedule is not None:
                self._advance_schedule(cursor, schedule, now)
        return messages

    def is_quiet(self, preference: ProactiveChatPreferences, now: datetime) -> bool:
        local = now.astimezone(ZoneInfo(preference.timezone)).time()
        start, end = preference.quiet_start, preference.quiet_end
        if start == end:
            return False
        return start <= local < end if start < end else local >= start or local < end

    def quiet_end_after(self, preference: ProactiveChatPreferences, now: datetime) -> datetime:
        zone = ZoneInfo(preference.timezone)
        local_now = now.astimezone(zone)
        target_day = local_now.date()
        if (
            preference.quiet_start > preference.quiet_end
            and local_now.time() >= preference.quiet_start
        ):
            target_day += timedelta(days=1)
        local_target = datetime.combine(target_day, preference.quiet_end, tzinfo=zone)
        if local_target <= local_now:
            local_target += timedelta(days=1)
        return local_target.astimezone(UTC)

    def _insert_job(
        self,
        cursor,
        schedule_id: str | None,
        user_id: str,
        conversation_id: str | None,
        scheduled_for: datetime,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO proactive_chat_jobs (
                job_id, schedule_id, user_id, conversation_id, scheduled_for
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (schedule_id, scheduled_for) DO UPDATE SET
                status = 'pending',
                error_code = NULL,
                lease_expires_at = NULL,
                updated_at = NOW()
            """,
            (
                f"proactive_job_{uuid.uuid4().hex}",
                schedule_id,
                user_id,
                conversation_id,
                scheduled_for,
            ),
        )

    def _spontaneous_allowed(
        self,
        preference: ProactiveChatPreferences,
        last_user_at: datetime,
        now: datetime,
    ) -> bool:
        min_gap, maximum, window = _LEVEL_LIMITS[preference.proactivity_level]
        if preference.consecutive_unanswered >= 2:
            return False
        if now - last_user_at < min_gap:
            return False
        if preference.last_proactive_at and now - preference.last_proactive_at < min_gap:
            return False
        if preference.window_started_at and now - preference.window_started_at < window:
            return preference.proactive_count < maximum
        return True

    def _mark_preference_delivery(
        self, cursor, preference: ProactiveChatPreferences, now: datetime
    ) -> None:
        _, maximum, window = _LEVEL_LIMITS[preference.proactivity_level]
        if preference.window_started_at is None or now - preference.window_started_at >= window:
            count, started_at = 1, now
        else:
            count, started_at = (
                min(preference.proactive_count + 1, maximum),
                preference.window_started_at,
            )
        cursor.execute(
            """
            UPDATE proactive_chat_preferences
            SET last_proactive_at = %s, proactive_count = %s, window_started_at = %s,
                consecutive_unanswered = consecutive_unanswered + 1, updated_at = NOW()
            WHERE user_id = %s
            """,
            (now, count, started_at, preference.user_id),
        )

    def _advance_schedule(self, cursor, schedule: ChatSchedule, now: datetime) -> None:
        if schedule.schedule_type == "once":
            cursor.execute(
                "DELETE FROM chat_schedules WHERE schedule_id = %s",
                (schedule.schedule_id,),
            )
            return
        delta = timedelta(days=1 if schedule.schedule_type == "daily" else 7)
        next_run_at = schedule.next_run_at + delta
        while next_run_at <= now:
            next_run_at += delta
        cursor.execute(
            """
            UPDATE chat_schedules
            SET run_count = run_count + 1, last_run_at = %s, next_run_at = %s,
                updated_at = NOW()
            WHERE schedule_id = %s
            """,
            (now, next_run_at, schedule.schedule_id),
        )
        self._insert_job(
            cursor, schedule.schedule_id, schedule.user_id, schedule.conversation_id, next_run_at
        )
