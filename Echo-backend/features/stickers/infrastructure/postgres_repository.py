from __future__ import annotations

import json
import uuid

from db.postgres_connection import get_connection, transaction
from features.auth.public import ensure_user_identity
from features.stickers.domain.entities import Sticker


def _sticker(row) -> Sticker:
    tags = row["semantic_tags"] or []
    if isinstance(tags, str):
        tags = json.loads(tags)
    return Sticker(
        sticker_id=row["sticker_id"],
        owner_type=row["owner_type"],
        source=row["source"],
        url=row["public_url"] or "",
        content_type=row["content_type"],
        description=row["description"],
        semantic_tags=tuple(tags),
        status=row["status"],
        created_at=row["created_at"],
    )


class PostgresStickerRepository:
    def create_upload(
        self,
        user_id: str,
        storage_key: str,
        public_url: str,
        content_type: str,
        byte_size: int,
        content_hash: str,
        description: str,
        tags: tuple[str, ...],
    ) -> Sticker:
        sticker_id = f"stk_{uuid.uuid4().hex}"
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO stickers (
                        sticker_id,owner_type,owner_user_id,source,storage_key,public_url,
                        content_type,byte_size,perceptual_hash,description,semantic_tags,
                        status,moderation_status
                    ) VALUES (%s,'user',%s,'uploaded',%s,%s,%s,%s,%s,%s,%s::jsonb,
                        'processing','pending') RETURNING *
                    """,
                    (
                        sticker_id, user_id, storage_key, public_url, content_type, byte_size,
                        content_hash, description[:300], json.dumps(tags, ensure_ascii=False),
                    ),
                )
                row = cursor.fetchone()
        return _sticker(row)

    def confirm(self, user_id: str, sticker_id: str) -> Sticker | None:
        # v1 has no external moderation provider: explicit confirmation activates a validated file.
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE stickers SET status='active', moderation_status='approved', updated_at=NOW()
                WHERE sticker_id=%s AND owner_user_id=%s AND status='processing'
                RETURNING *
                """,
                (sticker_id, user_id),
            )
            row = cursor.fetchone()
        return _sticker(row) if row else None

    def list(self, user_id: str, query: str = "", limit: int = 50) -> list[Sticker]:
        params: list[object] = [user_id]
        where = "status='active' AND (owner_type='echo' OR owner_user_id=%s)"
        if query.strip():
            where += " AND (description ILIKE %s OR semantic_tags::text ILIKE %s)"
            term = f"%{query.strip()}%"
            params.extend([term, term])
        params.append(limit)
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM stickers WHERE {where} ORDER BY created_at DESC LIMIT %s",
                params,
            )
            rows = cursor.fetchall()
        return [_sticker(row) for row in rows]

    def get(self, user_id: str, sticker_id: str) -> Sticker | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM stickers WHERE sticker_id=%s AND status='active'
                AND (owner_type='echo' OR owner_user_id=%s)
                """,
                (sticker_id, user_id),
            )
            row = cursor.fetchone()
        return _sticker(row) if row else None

    def delete(self, user_id: str, sticker_id: str) -> str | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE stickers SET status='deleted',updated_at=NOW()
                WHERE sticker_id=%s AND owner_user_id=%s AND owner_type='user'
                RETURNING storage_key
                """,
                (sticker_id, user_id),
            )
            row = cursor.fetchone()
        return row["storage_key"] if row else None

    def create_generation_job(self, user_id: str, prompt: str, intent: str) -> str:
        job_id = f"sticker_job_{uuid.uuid4().hex}"
        with transaction() as conn:
            ensure_user_identity(user_id=user_id, conn=conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sticker_generation_jobs(job_id,user_id,prompt,normalized_intent)
                    VALUES (%s,%s,%s,%s)
                    """,
                    (job_id, user_id, prompt[:1000], intent[:100]),
                )
        return job_id

    def generation_job(self, user_id: str, job_id: str) -> dict | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """SELECT job_id,status,generated_sticker_id,error_code,created_at,finished_at
                FROM sticker_generation_jobs WHERE user_id=%s AND job_id=%s""",
                (user_id, job_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def claim_generation_jobs(self, limit: int) -> list[dict]:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                WITH candidates AS (
                    SELECT id FROM sticker_generation_jobs
                    WHERE status IN ('pending','retry') ORDER BY id
                    FOR UPDATE SKIP LOCKED LIMIT %s
                )
                UPDATE sticker_generation_jobs j SET status='running',attempts=attempts+1
                FROM candidates c WHERE j.id=c.id
                RETURNING j.job_id,j.user_id,j.prompt,j.normalized_intent,j.attempts
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def complete_generation(
        self,
        job_id: str,
        user_id: str,
        storage_key: str,
        public_url: str,
        content_type: str,
        byte_size: int,
        content_hash: str,
        intent: str,
    ) -> None:
        sticker_id = f"stk_{uuid.uuid4().hex}"
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stickers (
                    sticker_id,owner_type,owner_user_id,source,storage_key,public_url,
                    content_type,byte_size,perceptual_hash,description,semantic_tags,
                    status,moderation_status
                ) VALUES (%s,'user',%s,'generated',%s,%s,%s,%s,%s,%s,%s::jsonb,
                    'active','approved')
                """,
                (
                    sticker_id,user_id,storage_key,public_url,content_type,byte_size,
                    content_hash,intent,json.dumps([intent] if intent else [], ensure_ascii=False),
                ),
            )
            cursor.execute(
                """UPDATE sticker_generation_jobs SET status='completed',
                generated_sticker_id=%s,finished_at=NOW() WHERE job_id=%s""",
                (sticker_id, job_id),
            )

    def fail_generation(self, job_id: str, error_code: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """UPDATE sticker_generation_jobs SET
                status=CASE WHEN attempts < 3 THEN 'retry' ELSE 'failed' END,
                error_code=%s,finished_at=CASE WHEN attempts >= 3 THEN NOW() ELSE NULL END
                WHERE job_id=%s""",
                (error_code[:120], job_id),
            )

