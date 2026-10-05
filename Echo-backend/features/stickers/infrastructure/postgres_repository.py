from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from db.postgres_connection import get_connection, transaction
from shared.config import settings

from features.auth.public import ensure_user_identity
from features.stickers.domain.entities import Sticker
from features.stickers.infrastructure.urls import resolve_sticker_url


def _sticker(row) -> Sticker:
    tags = row["semantic_tags"] or []
    if isinstance(tags, str):
        tags = json.loads(tags)
    return Sticker(
        sticker_id=row["sticker_id"],
        owner_type=row["owner_type"],
        source=row["source"],
        url=resolve_sticker_url(
            source=str(row["source"] or ""),
            storage_key=str(row["storage_key"] or ""),
            public_url=str(row["public_url"] or ""),
        ),
        content_type=row["content_type"],
        description=row["description"],
        semantic_tags=tuple(tags),
        status=row["status"],
        created_at=row["created_at"],
        priority=int(row.get("priority") or 100),
        similarity_score=(
            float(row["similarity_score"])
            if row.get("similarity_score") is not None
            else None
        ),
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def sticker_row_visible_to_user(row, user_id: str) -> bool:
    return row.get("owner_type") == "echo" or row.get("owner_user_id") == user_id


def filter_semantically_close_rows(rows: list, maximum_score_gap: float) -> list:
    if not rows:
        return []
    best_score = max(float(row.get("similarity_score") or 0.0) for row in rows)
    return [
        row
        for row in rows
        if best_score - float(row.get("similarity_score") or 0.0) <= maximum_score_gap
    ]


def rank_sticker_rows(
    rows: list,
    *,
    terms: tuple[str, ...],
    purpose: str,
    recent_ids: set[str],
    last_used: dict[str, datetime],
    now: datetime,
    cooldown: timedelta,
) -> list:
    del purpose
    terms_lower = tuple(term.lower() for term in terms)
    normalized_query = " ".join(terms_lower)

    def score(row) -> tuple[int, int, int, datetime]:
        raw_tags = row["semantic_tags"] or []
        if isinstance(raw_tags, str):
            raw_tags = json.loads(raw_tags)
        tags = tuple(str(tag).lower() for tag in raw_tags)
        description = str(row["description"] or "").lower()
        similarity = float(row.get("similarity_score") or 0.0)
        semantic_score = int(similarity * 1000)
        for term in terms_lower:
            if term in tags:
                semantic_score += 100
            elif any(term in tag for tag in tags):
                semantic_score += 70
            elif term == description:
                semantic_score += 60
            elif term in description:
                semantic_score += 40
        for tag in tags:
            if tag and tag in normalized_query:
                semantic_score += 100
        if description and description in normalized_query:
            semantic_score += 60
        owner_score = 10 if row["owner_type"] == "echo" else 0
        sticker_id = str(row["sticker_id"])
        last_used_at = last_used.get(sticker_id)
        within_time_cooldown = bool(
            last_used_at is not None and now - last_used_at < cooldown
        )
        cooling_penalty = -1 if sticker_id in recent_ids or within_time_cooldown else 0
        created_at = row["created_at"] or datetime.min.replace(tzinfo=UTC)
        return (
            cooling_penalty,
            semantic_score + owner_score,
            int(row.get("priority") or 100),
            created_at,
        )

    ordered = sorted(rows, key=score, reverse=True)
    eligible = [row for row in ordered if score(row)[0] == 0]
    return eligible or ordered


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

    def list(
        self,
        user_id: str,
        query: str = "",
        limit: int = 100,
        *,
        conversation_id: str | None = None,
        purpose: str = "explicit_request",
        include_echo: bool = True,
        include_user: bool = True,
    ) -> list[Sticker]:
        if not include_echo and not include_user:
            return []
        params: list[object] = []
        if include_echo and include_user:
            owner_clause = "(owner_type='echo' OR owner_user_id=%s)"
            params.append(user_id)
        elif include_echo:
            owner_clause = "owner_type='echo'"
        else:
            owner_clause = "owner_type='user' AND owner_user_id=%s"
            params.append(user_id)
        where = f"status='active' AND {owner_clause}"
        terms = [
            term
            for term in re.split(r"[\s,，、;；]+", query.strip())
            if term and term != "表情包"
        ][:8]
        if terms:
            predicates: list[str] = []
            for term in terms:
                predicates.append("(description ILIKE %s OR semantic_tags::text ILIKE %s)")
                pattern = f"%{term}%"
                params.extend([pattern, pattern])
            where += " AND (" + " OR ".join(predicates) + ")"
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM stickers WHERE {where}",
                params,
            )
            rows = [
                row
                for row in cursor.fetchall()
                if sticker_row_visible_to_user(row, user_id)
            ]
            recent_ids, last_used = self._recent_usage(
                conn,
                user_id=user_id,
                conversation_id=conversation_id,
                recent_turns=settings.sticker_reuse_cooldown_turns,
            )

        selected = rank_sticker_rows(
            rows,
            terms=tuple(terms),
            purpose=purpose,
            recent_ids=recent_ids,
            last_used=last_used,
            now=datetime.now(UTC),
            cooldown=timedelta(minutes=settings.sticker_reuse_cooldown_minutes),
        )
        return [_sticker(row) for row in selected[:limit]]

    def list_vector_matches(
        self,
        user_id: str,
        query: str,
        query_embedding: list[float],
        embedding_model: str,
        limit: int,
        *,
        conversation_id: str | None = None,
        purpose: str = "explicit_request",
        score_threshold: float = 0.25,
        maximum_score_gap: float = 0.04,
    ) -> list[Sticker]:
        if not query_embedding:
            return []
        vector = _vector_literal(query_embedding)
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sticker.*,
                       1 - (embedding.embedding <=> %s::vector) AS similarity_score
                FROM sticker_embeddings embedding
                JOIN stickers sticker ON sticker.sticker_id = embedding.sticker_id
                WHERE embedding.embedding_model = %s
                  AND sticker.status = 'active'
                  AND (sticker.owner_type = 'echo' OR sticker.owner_user_id = %s)
                  AND 1 - (embedding.embedding <=> %s::vector) >= %s
                ORDER BY embedding.embedding <=> %s::vector,
                         sticker.priority DESC,
                         sticker.created_at DESC
                LIMIT %s
                """,
                (
                    vector,
                    embedding_model,
                    user_id,
                    vector,
                    score_threshold,
                    vector,
                    max(limit, 1),
                ),
            )
            rows = [
                row
                for row in cursor.fetchall()
                if sticker_row_visible_to_user(row, user_id)
            ]
            rows = filter_semantically_close_rows(rows, maximum_score_gap)
            recent_ids, last_used = self._recent_usage(
                conn,
                user_id=user_id,
                conversation_id=conversation_id,
                recent_turns=settings.sticker_reuse_cooldown_turns,
            )

        terms = tuple(
            term
            for term in re.split(r"[\s,，、;；]+", query.strip())
            if term
        )[:8]
        selected = rank_sticker_rows(
            rows,
            terms=terms or (query.strip(),),
            purpose=purpose,
            recent_ids=recent_ids,
            last_used=last_used,
            now=datetime.now(UTC),
            cooldown=timedelta(minutes=settings.sticker_reuse_cooldown_minutes),
        )
        return [_sticker(row) for row in selected[:limit]]

    def list_active_for_embedding(self, limit: int) -> list[Sticker]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM stickers
                WHERE status = 'active'
                ORDER BY id
                LIMIT %s
                """,
                (max(limit, 1),),
            )
            rows = cursor.fetchall()
        return [_sticker(row) for row in rows]

    def list_embedding_metadata(self, embedding_model: str) -> dict[str, str]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sticker_id, semantic_text
                FROM sticker_embeddings
                WHERE embedding_model = %s
                """,
                (embedding_model,),
            )
            rows = cursor.fetchall()
        return {str(row["sticker_id"]): str(row["semantic_text"]) for row in rows}

    def upsert_embedding(
        self,
        sticker_id: str,
        embedding_model: str,
        semantic_text: str,
        embedding: list[float],
    ) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sticker_embeddings (
                    sticker_id, embedding_model, semantic_text, embedding
                ) VALUES (%s, %s, %s, %s::vector)
                ON CONFLICT(sticker_id) DO UPDATE SET
                    embedding_model = EXCLUDED.embedding_model,
                    semantic_text = EXCLUDED.semantic_text,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                (
                    sticker_id,
                    embedding_model,
                    semantic_text,
                    _vector_literal(embedding),
                ),
            )

    @staticmethod
    def _recent_usage(
        conn,
        *,
        user_id: str,
        conversation_id: str | None,
        recent_turns: int,
    ) -> tuple[set[str], dict[str, datetime]]:
        clauses = [
            "message.user_id = %s",
            "message.role = 'assistant'",
            "attachment.attachment_type = 'sticker'",
        ]
        params: list[object] = [user_id]
        if conversation_id:
            clauses.append("message.conversation_id = %s")
            params.append(conversation_id)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT message.message_id, message.reply_group_id,
                       attachment.resource_id, message.created_at
                FROM chat_messages message
                JOIN chat_message_attachments attachment
                  ON attachment.message_id = message.message_id
                WHERE {' AND '.join(clauses)}
                ORDER BY message.created_at DESC
                LIMIT 100
                """,
                params,
            )
            rows = cursor.fetchall()

        recent_ids: set[str] = set()
        last_used: dict[str, datetime] = {}
        seen_groups: list[str] = []
        for row in rows:
            sticker_id = str(row["resource_id"] or "")
            if not sticker_id:
                continue
            created_at = row["created_at"]
            if created_at is not None and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if created_at is not None and (
                sticker_id not in last_used or created_at > last_used[sticker_id]
            ):
                last_used[sticker_id] = created_at
            group = str(row["reply_group_id"] or f"message:{row['message_id']}")
            if group not in seen_groups and len(seen_groups) < recent_turns:
                seen_groups.append(group)
            if group in seen_groups:
                recent_ids.add(sticker_id)
        return recent_ids, last_used

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
        return _sticker(row) if row and sticker_row_visible_to_user(row, user_id) else None

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
            if row:
                cursor.execute(
                    "DELETE FROM sticker_embeddings WHERE sticker_id = %s",
                    (sticker_id,),
                )
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

