from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db.postgres_connection import get_connection, transaction
from features.auth.public import ensure_user_identity
from features.letters.domain.entities import DailyLetter, LetterPreference
from shared.config import settings


def _letter(row) -> DailyLetter:
    return DailyLetter(
        letter_id=row["letter_id"],
        local_date=row["local_date"],
        timezone=row["timezone"],
        status=row["status"],
        subject=row["subject"],
        content=row["content"],
        published_at=row["published_at"],
        read_at=row["read_at"],
    )


class PostgresLetterRepository:
    def exists(self, user_id: str, local_date: date) -> bool:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM daily_letters
                WHERE user_id=%s AND local_date=%s AND generation_version=%s
                """,
                (user_id, local_date, settings.daily_letter_generation_version),
            )
            return cursor.fetchone() is not None

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
                timezone=settings.default_user_timezone,
                publish_time=time.fromisoformat(settings.daily_letter_publish_time),
            )
        return LetterPreference(bool(row["enabled"]), row["timezone"], row["publish_time"])

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
        return [_letter(row) for row in rows]

    def get_letter(self, user_id: str, letter_id: str) -> DailyLetter | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM daily_letters WHERE user_id=%s AND letter_id=%s",
                (user_id, letter_id),
            )
            row = cursor.fetchone()
        return _letter(row) if row else None

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
        return _letter(row) if row else None

    def due_users(self, now_utc: datetime) -> list[tuple[str, LetterPreference, date]]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.user_id, COALESCE(p.enabled, TRUE) AS enabled,
                    COALESCE(p.timezone, %s) AS timezone,
                    COALESCE(p.publish_time, %s::time) AS publish_time
                FROM users u LEFT JOIN letter_preferences p ON p.user_id=u.user_id
                WHERE u.status='active' AND COALESCE(p.enabled, TRUE)=TRUE
                """,
                (settings.default_user_timezone, settings.daily_letter_publish_time),
            )
            rows = cursor.fetchall()
        due = []
        for row in rows:
            try:
                local_now = now_utc.astimezone(ZoneInfo(row["timezone"]))
            except ZoneInfoNotFoundError:
                continue
            publish_time = row["publish_time"]
            if local_now.time().replace(tzinfo=None) < publish_time:
                continue
            target_date = local_now.date().fromordinal(local_now.date().toordinal() - 1)
            due.append(
                (
                    row["user_id"],
                    LetterPreference(True, row["timezone"], publish_time),
                    target_date,
                )
            )
        return due

    def source_messages(self, user_id: str, local_date: date, timezone_name: str) -> list[dict]:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(local_date, time.max, zone).astimezone(timezone.utc)
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, created_at FROM chat_messages
                WHERE user_id=%s AND created_at BETWEEN %s AND %s AND status='active'
                ORDER BY id ASC LIMIT 80
                """,
                (user_id, start, end),
            )
            return [dict(row) for row in cursor.fetchall()]

    def create_ready(
        self,
        user_id: str,
        local_date: date,
        timezone_name: str,
        subject: str,
        content: str,
        source_ids: list[int],
    ) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO daily_letters (
                    letter_id,user_id,local_date,timezone,status,subject,content,
                    source_message_ids,generation_version,scheduled_at,generated_at,published_at
                ) VALUES (%s,%s,%s,%s,'ready',%s,%s,%s::jsonb,%s,NOW(),NOW(),NOW())
                ON CONFLICT(user_id,local_date,generation_version) DO NOTHING
                """,
                (
                    f"letter_{uuid.uuid4().hex}", user_id, local_date, timezone_name,
                    subject[:120], content[:4000], json.dumps(source_ids),
                    settings.daily_letter_generation_version,
                ),
            )
            return cursor.rowcount > 0

    def create_skipped(self, user_id: str, local_date: date, timezone_name: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO daily_letters (
                    letter_id,user_id,local_date,timezone,status,generation_version,
                    scheduled_at,generated_at,failure_code
                ) VALUES (%s,%s,%s,%s,'skipped',%s,NOW(),NOW(),'no_interaction')
                ON CONFLICT(user_id,local_date,generation_version) DO NOTHING
                """,
                (f"letter_{uuid.uuid4().hex}", user_id, local_date, timezone_name,
                 settings.daily_letter_generation_version),
            )
