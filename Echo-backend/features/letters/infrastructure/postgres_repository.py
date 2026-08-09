from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db.postgres_connection import get_connection, transaction
from shared.config import settings

from features.auth.public import ensure_user_identity
from features.letters.domain.entities import (
    DailyLetter,
    LetterGenerationTask,
    LetterPreference,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LetterRepositoryConfig:
    default_timezone: str
    default_publish_time: str
    generation_time: str
    generation_version: str
    maximum_attempts: int
    lease_seconds: int
    retry_offsets_seconds: tuple[int, ...]


def _default_config() -> LetterRepositoryConfig:
    image_seconds = 0
    if settings.letter_image_generation_enabled:
        image_seconds = (
            settings.minimax_image_timeout_seconds * settings.letter_image_max_attempts
        )
    return LetterRepositoryConfig(
        default_timezone=settings.default_user_timezone,
        default_publish_time=settings.daily_letter_publish_time,
        generation_time=settings.daily_letter_generation_time,
        generation_version=settings.daily_letter_generation_version,
        maximum_attempts=settings.daily_letter_max_attempts,
        lease_seconds=settings.daily_letter_agent_timeout_seconds + image_seconds + 120,
        retry_offsets_seconds=_retry_offsets(settings.daily_letter_retry_offsets_seconds),
    )


def _retry_offsets(value: str) -> tuple[int, ...]:
    offsets = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if any(offset <= 0 for offset in offsets):
        raise ValueError("Daily letter retry offsets must be positive")
    return offsets


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


class PostgresLetterRepository:
    def __init__(self, config: LetterRepositoryConfig | None = None):
        self.config = config or _default_config()

    def _image_url(self, row: Any) -> str:
        storage_key = str(row.get("image_storage_key") or "").strip()
        if not storage_key:
            return ""
        try:
            from shared.storage.cos_storage import get_cos_object_storage

            return get_cos_object_storage().download_url(storage_key)
        except Exception:
            logger.warning(
                "Unable to create letter image URL letter_id=%s",
                row.get("letter_id"),
                exc_info=True,
            )
            return ""

    def _letter(self, row: Any) -> DailyLetter:
        return DailyLetter(
            letter_id=str(row["letter_id"]),
            local_date=row["local_date"],
            timezone=str(row["timezone"]),
            status=str(row["status"]),
            subject=str(row["subject"] or ""),
            content=str(row["content"] or ""),
            published_at=row["published_at"],
            read_at=row["read_at"],
            image_url=self._image_url(row),
            image_width=(int(row["image_width"]) if row.get("image_width") is not None else None),
            image_height=(
                int(row["image_height"]) if row.get("image_height") is not None else None
            ),
        )

    def get_preference(self, user_id: str) -> LetterPreference:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT enabled, timezone, publish_time FROM letter_preferences WHERE user_id=%s",
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            return LetterPreference(
                enabled=True,
                timezone=self.config.default_timezone,
                publish_time=time.fromisoformat(self.config.default_publish_time),
            )
        return LetterPreference(bool(row["enabled"]), str(row["timezone"]), row["publish_time"])

    def save_preference(
        self, user_id: str, enabled: bool, timezone_name: str, publish_time: time
    ) -> LetterPreference:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO letter_preferences (user_id, enabled, timezone, publish_time)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET enabled=EXCLUDED.enabled,
                        timezone=EXCLUDED.timezone, publish_time=EXCLUDED.publish_time,
                        updated_at=NOW()
                    """,
                    (user_id, enabled, timezone_name, publish_time),
                )
        return LetterPreference(enabled, timezone_name, publish_time)

    def list_letters(self, user_id: str, limit: int = 20) -> list[DailyLetter]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM daily_letters WHERE user_id=%s AND status IN ('ready','read')
                ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cursor.fetchall()
        return [self._letter(row) for row in rows]

    def get_letter(self, user_id: str, letter_id: str) -> DailyLetter | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM daily_letters
                WHERE user_id=%s AND letter_id=%s AND status IN ('ready', 'read')
                """,
                (user_id, letter_id),
            )
            row = cursor.fetchone()
        return self._letter(row) if row else None

    def mark_read(self, user_id: str, letter_id: str) -> DailyLetter | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters SET status='read', read_at=COALESCE(read_at,NOW()),
                    updated_at=NOW() WHERE user_id=%s AND letter_id=%s
                    AND status IN ('ready','read') RETURNING *
                """,
                (user_id, letter_id),
            )
            row = cursor.fetchone()
        return self._letter(row) if row else None

    def _active_preferences(self) -> list[tuple[str, LetterPreference]]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.user_id, COALESCE(p.enabled, TRUE) AS enabled,
                    COALESCE(p.timezone, %s) AS timezone,
                    COALESCE(p.publish_time, %s::time) AS publish_time
                FROM users u LEFT JOIN letter_preferences p ON p.user_id=u.user_id
                WHERE u.status='active' AND COALESCE(p.enabled, TRUE)=TRUE
                """,
                (self.config.default_timezone, self.config.default_publish_time),
            )
            rows = cursor.fetchall()
        return [
            (
                str(row["user_id"]),
                LetterPreference(bool(row["enabled"]), str(row["timezone"]), row["publish_time"]),
            )
            for row in rows
        ]

    @staticmethod
    def _local_time(value: str) -> time:
        try:
            return time.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid letter time: {value}") from exc

    def ensure_due_generation_tasks(self, now_utc: datetime) -> int:
        generation_time = self._local_time(self.config.generation_time)
        created = 0
        for user_id, preference in self._active_preferences():
            try:
                zone = ZoneInfo(preference.timezone)
            except ZoneInfoNotFoundError:
                logger.warning("Skipping letter user with invalid timezone user_id=%s", user_id)
                continue
            local_now = now_utc.astimezone(zone)
            if local_now.time().replace(tzinfo=None) < generation_time:
                continue
            local_date = local_now.date() - timedelta(days=1)
            scheduled_at = datetime.combine(
                local_now.date(), generation_time, tzinfo=zone
            ).astimezone(UTC)
            publish_at = datetime.combine(
                local_now.date(), preference.publish_time, tzinfo=zone
            ).astimezone(UTC)
            if publish_at < scheduled_at:
                publish_at += timedelta(days=1)
            with transaction() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO daily_letters (
                        letter_id, user_id, local_date, timezone, status,
                        generation_version, scheduled_at, publish_at,
                        generation_attempt_count, max_attempts, next_attempt_at
                    ) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, 0, %s, %s)
                    ON CONFLICT (user_id, local_date, generation_version) DO NOTHING
                    """,
                    (
                        f"letter_{uuid.uuid4().hex}",
                        user_id,
                        local_date,
                        preference.timezone,
                        self.config.generation_version,
                        scheduled_at,
                        publish_at,
                        self.config.maximum_attempts,
                        now_utc,
                    ),
                )
                created += max(cursor.rowcount, 0)
        return created

    def claim_generation_task(self, now_utc: datetime) -> LetterGenerationTask | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters
                SET status='failed', failure_code='publication_deadline_exceeded',
                    lease_expires_at=NULL, updated_at=%s
                WHERE status IN ('pending', 'retry_wait') AND publish_at <= %s
                """,
                (now_utc, now_utc),
            )
            cursor.execute(
                """
                UPDATE daily_letters
                SET status = CASE
                        WHEN generation_attempt_count < max_attempts AND publish_at > %s
                            THEN 'retry_wait'
                        ELSE 'failed'
                    END,
                    failure_code = CASE
                        WHEN generation_attempt_count < max_attempts AND publish_at > %s
                            THEN 'worker_lease_expired'
                        ELSE 'worker_lease_exhausted'
                    END,
                    next_attempt_at = CASE
                        WHEN generation_attempt_count < max_attempts AND publish_at > %s
                            THEN %s
                        ELSE next_attempt_at
                    END,
                    lease_expires_at = NULL,
                    updated_at = %s
                WHERE status = 'generating'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < %s
                """,
                (now_utc, now_utc, now_utc, now_utc, now_utc, now_utc),
            )
            cursor.execute(
                """
                SELECT * FROM daily_letters
                WHERE status IN ('pending', 'retry_wait')
                  AND scheduled_at <= %s
                  AND COALESCE(next_attempt_at, %s) <= %s
                  AND publish_at > %s
                ORDER BY scheduled_at ASC, id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (now_utc, now_utc, now_utc, now_utc),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                UPDATE daily_letters
                SET status='generating', generation_attempt_count=generation_attempt_count + 1,
                    lease_expires_at=%s + (%s * INTERVAL '1 second'), updated_at=%s
                WHERE letter_id=%s RETURNING *
                """,
                (now_utc, self.config.lease_seconds, now_utc, row["letter_id"]),
            )
            claimed = cursor.fetchone()
        return LetterGenerationTask(
            letter_id=str(claimed["letter_id"]),
            user_id=str(claimed["user_id"]),
            local_date=claimed["local_date"],
            timezone=str(claimed["timezone"]),
            scheduled_at=claimed["scheduled_at"],
            publish_at=claimed["publish_at"],
            attempt_count=int(claimed["generation_attempt_count"]),
            max_attempts=int(claimed["max_attempts"]),
        )

    def source_messages(
        self,
        user_id: str,
        local_date: date,
        timezone_name: str,
    ) -> list[dict[str, Any]]:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(local_date, time.min, zone).astimezone(UTC)
        end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(UTC)
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT message.id, message.message_id, message.role, message.content,
                       message.message_type, message.created_at,
                       COALESCE(
                           jsonb_agg(
                               jsonb_build_object(
                                   'type', attachment.attachment_type,
                                   'resource_id', attachment.resource_id,
                                   'description', COALESCE(sticker.description, ''),
                                   'semantic_tags', COALESCE(sticker.semantic_tags, '[]'::jsonb)
                               ) ORDER BY attachment.position
                           ) FILTER (WHERE attachment.id IS NOT NULL),
                           '[]'::jsonb
                       ) AS attachments
                FROM chat_messages message
                LEFT JOIN chat_message_attachments attachment
                  ON attachment.message_id = message.message_id
                 AND attachment.user_id = message.user_id
                LEFT JOIN stickers sticker ON sticker.sticker_id = attachment.resource_id
                WHERE message.user_id=%s
                  AND message.created_at >= %s
                  AND message.created_at < %s
                  AND message.status='active'
                GROUP BY message.id, message.message_id, message.role, message.content,
                         message.message_type, message.created_at
                ORDER BY message.id ASC
                """,
                (user_id, start, end),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "message_id": str(row["message_id"] or ""),
                "role": str(row["role"]),
                "content": str(row["content"] or ""),
                "message_type": str(row["message_type"] or "text"),
                "created_at": row["created_at"],
                "attachments": _json(row["attachments"], []),
            }
            for row in rows
        ]

    def complete_generation(
        self,
        task: LetterGenerationTask,
        *,
        subject: str,
        content: str,
        reflection: str,
        mood: str,
        image_brief: dict,
        source_message_ids: list[int],
        source_memory_ids: list[str],
        agent_run_id: str = "",
        context_version: str = "",
        context_snapshot: dict[str, object] | None = None,
        image_storage_key: str = "",
        image_content_type: str = "",
        image_width: int | None = None,
        image_height: int | None = None,
        image_byte_size: int | None = None,
        image_provider: str = "",
        image_model: str = "",
        image_reference_version: str = "",
        image_status: str = "disabled",
        image_failure_code: str | None = None,
    ) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters
                SET status='ready_to_publish', subject=%s, content=%s,
                    reflection=%s, mood=%s, image_brief=%s::jsonb,
                    source_message_ids=%s::jsonb, source_memory_ids=%s::jsonb,
                    agent_run_id=%s, context_version=%s, context_snapshot=%s::jsonb,
                    image_storage_key=%s, image_content_type=%s, image_width=%s,
                    image_height=%s, image_byte_size=%s, image_provider=%s,
                    image_model=%s, image_reference_version=%s,
                    image_generation_status=%s, image_failure_code=%s,
                    generated_at=NOW(), lease_expires_at=NULL, failure_code=NULL,
                    updated_at=NOW()
                WHERE letter_id=%s AND user_id=%s AND status='generating'
                """,
                (
                    subject[:120],
                    content[:4000],
                    reflection[:1200],
                    mood[:80],
                    json.dumps(image_brief, ensure_ascii=False),
                    json.dumps(source_message_ids),
                    json.dumps(source_memory_ids, ensure_ascii=False),
                    agent_run_id,
                    context_version,
                    json.dumps(context_snapshot or {}, ensure_ascii=False),
                    image_storage_key,
                    image_content_type,
                    image_width,
                    image_height,
                    image_byte_size,
                    image_provider,
                    image_model,
                    image_reference_version,
                    image_status,
                    image_failure_code,
                    task.letter_id,
                    task.user_id,
                ),
            )
            return cursor.rowcount > 0

    def create_skipped(self, task: LetterGenerationTask, reason: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters
                SET status='skipped', failure_code=%s, generated_at=NOW(),
                    lease_expires_at=NULL, updated_at=NOW()
                WHERE letter_id=%s AND user_id=%s AND status='generating'
                """,
                (reason[:120], task.letter_id, task.user_id),
            )
            return cursor.rowcount > 0

    def fail_generation(
        self,
        task: LetterGenerationTask,
        error_code: str,
        now_utc: datetime,
    ) -> None:
        retry_index = task.attempt_count - 1
        has_retry_offset = retry_index < len(self.config.retry_offsets_seconds)
        next_attempt_at = (
            task.scheduled_at + timedelta(seconds=self.config.retry_offsets_seconds[retry_index])
            if has_retry_offset
            else None
        )
        retryable = (
            task.attempt_count < task.max_attempts
            and next_attempt_at is not None
            and next_attempt_at < task.publish_at
        )
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters
                SET status=%s,
                    next_attempt_at=CASE WHEN %s THEN %s ELSE next_attempt_at END,
                    failure_code=%s, lease_expires_at=NULL, updated_at=%s
                WHERE letter_id=%s AND user_id=%s AND status='generating'
                """,
                (
                    "retry_wait" if retryable else "failed",
                    retryable,
                    next_attempt_at,
                    error_code[:120],
                    now_utc,
                    task.letter_id,
                    task.user_id,
                ),
            )

    def publish_due(self, now_utc: datetime) -> int:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE daily_letters
                SET status='ready', published_at=COALESCE(published_at, %s), updated_at=%s
                WHERE status='ready_to_publish' AND publish_at <= %s
                """,
                (now_utc, now_utc, now_utc),
            )
            return max(cursor.rowcount, 0)
