from __future__ import annotations

from dataclasses import dataclass

from db.postgres_connection import get_connection, transaction


@dataclass(frozen=True)
class NotificationOutboxItem:
    notification_id: str
    user_id: str
    title: str
    body_policy: str
    body: str
    payload: dict[str, object]
    attempt_count: int


@dataclass(frozen=True)
class PushTarget:
    device_id: str
    token: str


class PostgresPushRepository:
    def claim_due(self) -> NotificationOutboxItem | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM notification_outbox
                WHERE status IN ('pending', 'retry_wait')
                  AND next_attempt_at <= NOW()
                ORDER BY next_attempt_at ASC, id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """
                UPDATE notification_outbox
                SET status = 'sending', attempt_count = attempt_count + 1,
                    updated_at = NOW()
                WHERE notification_id = %s
                RETURNING *
                """,
                (row["notification_id"],),
            )
            claimed = cursor.fetchone()
        return NotificationOutboxItem(
            notification_id=str(claimed["notification_id"]),
            user_id=str(claimed["user_id"]),
            title=str(claimed["title"] or "Echo"),
            body_policy=str(claimed["body_policy"]),
            body=str(claimed["body"] or ""),
            payload=dict(claimed["payload"] or {}),
            attempt_count=int(claimed["attempt_count"]),
        )

    def list_targets(self, user_id: str) -> tuple[PushTarget, ...]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT device_id, token FROM push_targets
                WHERE user_id = %s AND status = 'active' AND provider = 'getui'
                ORDER BY last_seen_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return tuple(
            PushTarget(device_id=str(row["device_id"]), token=str(row["token"])) for row in rows
        )

    def mark_sent(self, notification_id: str, device_ids: tuple[str, ...]) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notification_outbox
                SET status = 'sent', last_error_code = NULL, updated_at = NOW()
                WHERE notification_id = %s
                """,
                (notification_id,),
            )
            if device_ids:
                cursor.execute(
                    """
                    UPDATE push_targets
                    SET last_success_at = NOW(), updated_at = NOW()
                    WHERE device_id = ANY(%s) AND status = 'active'
                    """,
                    (list(device_ids),),
                )

    def mark_retry(self, item: NotificationOutboxItem, error_code: str) -> None:
        terminal = item.attempt_count >= 3
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notification_outbox
                SET status = %s,
                    next_attempt_at = CASE
                        WHEN %s THEN next_attempt_at
                        ELSE NOW() + (%s * INTERVAL '1 second')
                    END,
                    last_error_code = %s,
                    updated_at = NOW()
                WHERE notification_id = %s
                """,
                (
                    "failed" if terminal else "retry_wait",
                    terminal,
                    min(60 * max(item.attempt_count, 1), 300),
                    error_code[:120],
                    item.notification_id,
                ),
            )

    def mark_discarded(self, notification_id: str, error_code: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notification_outbox
                SET status = 'discarded', last_error_code = %s, updated_at = NOW()
                WHERE notification_id = %s
                """,
                (error_code[:120], notification_id),
            )

    def invalidate_target(self, device_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE push_targets
                SET status = 'invalid', updated_at = NOW()
                WHERE device_id = %s
                """,
                (device_id,),
            )
