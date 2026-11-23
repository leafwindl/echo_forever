"""B站扫描任务的持久化：一个用户同时只允许一个任务，全局由单 worker 串行领取。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from db.postgres_connection import transaction
from psycopg.types.json import Jsonb


def create_or_get_scan_job(
    *,
    user_id: str,
    conversation_id: str,
    item_limit: int = 8,
) -> dict[str, Any]:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT job_id, status
            FROM bili_scan_jobs
            WHERE user_id = %s AND status IN ('pending', 'running')
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            return {
                "job_id": str(existing["job_id"]),
                "status": str(existing["status"]),
                "reused": True,
            }
        job_id = f"bili_scan_{uuid.uuid4().hex[:16]}"
        cursor.execute(
            """
            INSERT INTO bili_scan_jobs (job_id, user_id, conversation_id, item_limit)
            VALUES (%s, %s, %s, %s)
            RETURNING job_id, status
            """,
            (job_id, user_id, conversation_id, max(1, min(item_limit, 10))),
        )
        row = cursor.fetchone()
        return {
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "reused": False,
        }


def claim_next_scan_job() -> dict[str, Any] | None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, job_id, user_id, conversation_id, attempts, max_attempts, item_limit
            FROM bili_scan_jobs
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute(
            """
            UPDATE bili_scan_jobs
            SET status = 'running', attempts = attempts + 1,
                started_at = NOW(), updated_at = NOW()
            WHERE id = %s
            """,
            (row["id"],),
        )
        return dict(row)


def complete_scan_job(job_id: str, result: dict[str, Any]) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE bili_scan_jobs
            SET status = 'completed', result = %s, error = NULL,
                finished_at = NOW(), updated_at = NOW()
            WHERE job_id = %s
            """,
            (Jsonb(result), job_id),
        )


def fail_scan_job(job_id: str, error: str) -> str:
    """返回 retrying / failed / missing。"""
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT attempts, max_attempts FROM bili_scan_jobs WHERE job_id = %s",
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return "missing"
        if int(row["attempts"]) < int(row["max_attempts"]):
            cursor.execute(
                """
                UPDATE bili_scan_jobs
                SET status = 'pending', error = %s, updated_at = NOW()
                WHERE job_id = %s
                """,
                (error[:500], job_id),
            )
            return "retrying"
        cursor.execute(
            """
            UPDATE bili_scan_jobs
            SET status = 'failed', error = %s,
                finished_at = NOW(), updated_at = NOW()
            WHERE job_id = %s
            """,
            (error[:500], job_id),
        )
        return "failed"


def recover_running_scan_jobs() -> int:
    """进程重启后把残留的 running 放回队列。"""
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE bili_scan_jobs SET status = 'pending', updated_at = NOW() "
            "WHERE status = 'running'"
        )
        return cursor.rowcount


def cleanup_old_scan_jobs(*, days: int = 7) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM bili_scan_jobs
            WHERE status IN ('completed', 'failed') AND finished_at < %s
            """,
            (cutoff,),
        )
        return cursor.rowcount
