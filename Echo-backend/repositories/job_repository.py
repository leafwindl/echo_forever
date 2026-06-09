import json
import sqlite3
import uuid
from typing import Dict, List, Optional

from db.connection import get_connection, transaction

RUNNABLE_STATUSES = ("pending", "retry")


def _row_to_job(row) -> Dict[str, object]:
    return {
        "job_id": row[0],
        "job_type": row[1],
        "status": row[2],
        "payload": json.loads(row[3]),
        "attempts": int(row[4] or 0),
        "max_attempts": int(row[5] or 0),
        "error": row[6],
        "created_at": row[7],
        "updated_at": row[8],
        "started_at": row[9],
        "finished_at": row[10],
    }


def create_job(
    job_type: str,
    payload: Dict[str, object],
    max_attempts: int = 3,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    if conn is None:
        with transaction() as tx:
            return create_job(job_type, payload, max_attempts=max_attempts, conn=tx)

    job_id = f"job_{uuid.uuid4().hex}"
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO background_jobs (job_id, job_type, payload, max_attempts)
        VALUES (?, ?, ?, ?)
        """,
        (job_id, job_type, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), max_attempts),
    )
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, object]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT job_id, job_type, status, payload, attempts, max_attempts,
                   error, created_at, updated_at, started_at, finished_at
            FROM background_jobs
            WHERE job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
    return _row_to_job(row) if row else None


def claim_job(job_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    if conn is None:
        with transaction() as tx:
            return claim_job(job_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE background_jobs
        SET status = 'running',
            attempts = attempts + 1,
            error = NULL,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
          AND status IN ('pending', 'retry')
          AND attempts < max_attempts
        """,
        (job_id,),
    )
    return cursor.rowcount > 0


def complete_job(job_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    if conn is None:
        with transaction() as tx:
            return complete_job(job_id, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE background_jobs
        SET status = 'completed',
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        """,
        (job_id,),
    )
    return cursor.rowcount > 0


def fail_job(job_id: str, error: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    if conn is None:
        with transaction() as tx:
            return fail_job(job_id, error, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE background_jobs
        SET status = CASE
                WHEN attempts < max_attempts THEN 'retry'
                ELSE 'failed'
            END,
            error = ?,
            finished_at = CASE
                WHEN attempts < max_attempts THEN finished_at
                ELSE CURRENT_TIMESTAMP
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        """,
        (error[:1000], job_id),
    )
    return cursor.rowcount > 0


def list_runnable_jobs(job_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, object]]:
    query = """
        SELECT job_id, job_type, status, payload, attempts, max_attempts,
               error, created_at, updated_at, started_at, finished_at
        FROM background_jobs
        WHERE status IN ('pending', 'retry')
          AND attempts < max_attempts
    """
    params: list[object] = []
    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)
    query += " ORDER BY id ASC LIMIT ?"
    params.append(max(1, limit))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [_row_to_job(row) for row in rows]


def reset_running_jobs(job_type: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> int:
    if conn is None:
        with transaction() as tx:
            return reset_running_jobs(job_type, conn=tx)

    query = """
        UPDATE background_jobs
        SET status = CASE
                WHEN attempts < max_attempts THEN 'retry'
                ELSE 'failed'
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'running'
    """
    params: list[object] = []
    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)

    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.rowcount
