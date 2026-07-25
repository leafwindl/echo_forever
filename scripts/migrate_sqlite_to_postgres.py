from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))

from db.postgres_schema import build_postgres_schema_sql


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(BACKEND_ROOT / ".env")


def _open_sqlite_connection(database_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(database_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    )
    return cursor.fetchone() is not None


def _sqlite_columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in cursor.fetchall()}


def _ensure_schema(pg_cursor, vector_dimension: int) -> None:
    for statement in build_postgres_schema_sql(vector_dimension):
        pg_cursor.execute(statement)


def _safe_json_load(value):
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _decode_embedding(raw_value) -> list[float]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [float(value) for value in raw_value]
    text = str(raw_value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
    except json.JSONDecodeError:
        pass
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [float(value) for value in text.split(",") if str(value).strip()]


def _copy_users(sqlite_cursor, pg_cursor) -> int:
    if not _table_exists(sqlite_cursor, "users"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT user_id, openid, nickname, avatar_url, created_at, updated_at
        FROM users
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        pg_cursor.execute(
            """
            INSERT INTO users (user_id, openid, nickname, avatar_url, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'active', %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                openid = COALESCE(EXCLUDED.openid, users.openid),
                nickname = COALESCE(EXCLUDED.nickname, users.nickname),
                avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
                updated_at = EXCLUDED.updated_at
            """,
            (row["user_id"], row["openid"], row["nickname"], row["avatar_url"], row["created_at"], row["updated_at"]),
        )
        count += 1
    return count


def _map_message_reference(message_id_map: dict[int, int], source_message_id) -> int | None:
    if source_message_id is None:
        return None
    legacy_message_id = int(source_message_id)
    if legacy_message_id <= 0:
        return 0
    return message_id_map.get(legacy_message_id)


def _copy_conversations(sqlite_cursor, pg_cursor, message_id_map: dict[int, int]) -> int:
    if not _table_exists(sqlite_cursor, "conversations"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT conversation_id, user_id, title, summary, summary_message_id, status, created_at, updated_at
        FROM conversations
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        pg_cursor.execute(
            """
            INSERT INTO conversations (
                conversation_id, user_id, title, summary, summary_message_id, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, 'active'), %s, %s)
            ON CONFLICT(conversation_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                summary_message_id = EXCLUDED.summary_message_id,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["conversation_id"],
                row["user_id"],
                row["title"],
                row["summary"] or "",
                _map_message_reference(message_id_map, row["summary_message_id"]) or 0,
                row["status"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        count += 1
    return count


def _copy_chat_messages(sqlite_cursor, pg_cursor) -> tuple[int, dict[int, int]]:
    if not _table_exists(sqlite_cursor, "chat_messages"):
        return 0, {}
    sqlite_columns = _sqlite_columns(sqlite_cursor, "chat_messages")
    timestamp_column = "timestamp" if "timestamp" in sqlite_columns else "created_at"
    sqlite_cursor.execute(
        f"""
        SELECT id, user_id, conversation_id, role, content, message_type, {timestamp_column} AS timestamp
        FROM chat_messages
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    message_id_map: dict[int, int] = {}
    for row in rows:
        legacy_message_id = int(row["id"])
        message_id = f"sqlite_msg_{legacy_message_id}"
        pg_cursor.execute(
            """
            INSERT INTO chat_messages (
                message_id, user_id, conversation_id, role, content,
                message_type, source, status, summarized_at, delete_after, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', NULL, NULL, %s)
            ON CONFLICT(message_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                conversation_id = EXCLUDED.conversation_id,
                role = EXCLUDED.role,
                content = EXCLUDED.content,
                message_type = EXCLUDED.message_type,
                created_at = EXCLUDED.created_at
            RETURNING id
            """,
            (
                message_id,
                row["user_id"],
                row["conversation_id"],
                row["role"],
                row["content"],
                row["message_type"] or "text",
                "sqlite_migration",
                row["timestamp"],
            ),
        )
        inserted_row = pg_cursor.fetchone()
        message_id_map[legacy_message_id] = int(inserted_row[0])
        count += 1
    return count, message_id_map


def _copy_memories(sqlite_cursor, pg_cursor, message_id_map: dict[int, int]) -> int:
    if not _table_exists(sqlite_cursor, "user_memories"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT memory_id, user_id, memory_type, content, source_message_id,
               confidence, importance, status, created_at, updated_at, expires_at
        FROM user_memories
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        pg_cursor.execute(
            """
            INSERT INTO user_memories (
                memory_id, user_id, memory_type, content, source_message_id,
                confidence, importance, status, created_at, updated_at, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, 'active'), %s, %s, %s)
            ON CONFLICT(memory_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                memory_type = EXCLUDED.memory_type,
                content = EXCLUDED.content,
                source_message_id = EXCLUDED.source_message_id,
                confidence = EXCLUDED.confidence,
                importance = EXCLUDED.importance,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at,
                expires_at = EXCLUDED.expires_at
            """,
            (
                row["memory_id"],
                row["user_id"],
                row["memory_type"],
                row["content"],
                _map_message_reference(message_id_map, row["source_message_id"]),
                float(row["confidence"] or 0.8),
                int(row["importance"] or 3),
                row["status"],
                row["created_at"],
                row["updated_at"],
                row["expires_at"],
            ),
        )
        count += 1
    return count


def _copy_memory_embeddings(sqlite_cursor, pg_cursor, vector_dimension: int) -> int:
    if not _table_exists(sqlite_cursor, "memory_embeddings"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT memory_id, user_id, embedding_model, embedding, vector_store_id, created_at, updated_at
        FROM memory_embeddings
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        embedding = _decode_embedding(row["embedding"])
        if not embedding:
            continue
        if len(embedding) != vector_dimension:
            print(
                f"Skip memory_embedding memory_id={row['memory_id']} because dimension={len(embedding)} != {vector_dimension}"
            )
            continue
        pg_cursor.execute(
            """
            INSERT INTO memory_embeddings (
                memory_id, user_id, embedding_model, embedding, vector_store_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s::vector, %s, %s, %s)
            ON CONFLICT(memory_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                embedding_model = EXCLUDED.embedding_model,
                embedding = EXCLUDED.embedding,
                vector_store_id = EXCLUDED.vector_store_id,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["memory_id"],
                row["user_id"],
                row["embedding_model"],
                _vector_literal(embedding),
                row["vector_store_id"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        count += 1
    return count


def _copy_jobs(sqlite_cursor, pg_cursor) -> int:
    if not _table_exists(sqlite_cursor, "background_jobs"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT job_id, job_type, status, payload, attempts, max_attempts, error,
               created_at, updated_at, started_at, finished_at
        FROM background_jobs
        ORDER BY id ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        payload = _safe_json_load(row["payload"])
        pg_cursor.execute(
            """
            INSERT INTO background_jobs (
                job_id, job_type, status, payload, attempts, max_attempts,
                error, created_at, updated_at, started_at, finished_at
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(job_id) DO UPDATE SET
                job_type = EXCLUDED.job_type,
                status = EXCLUDED.status,
                payload = EXCLUDED.payload,
                attempts = EXCLUDED.attempts,
                max_attempts = EXCLUDED.max_attempts,
                error = EXCLUDED.error,
                updated_at = EXCLUDED.updated_at,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at
            """,
            (
                row["job_id"],
                row["job_type"],
                row["status"],
                json.dumps(payload, ensure_ascii=False),
                int(row["attempts"] or 0),
                int(row["max_attempts"] or 3),
                row["error"],
                row["created_at"],
                row["updated_at"],
                row["started_at"],
                row["finished_at"],
            ),
        )
        count += 1
    return count


def _copy_runtime_settings(sqlite_cursor, pg_cursor) -> int:
    if not _table_exists(sqlite_cursor, "runtime_settings"):
        return 0
    sqlite_cursor.execute(
        """
        SELECT key, value, updated_at
        FROM runtime_settings
        ORDER BY key ASC
        """
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        pg_cursor.execute(
            """
            INSERT INTO runtime_settings (key, value, scope, updated_by, updated_at)
            VALUES (%s, %s, 'global', NULL, %s)
            ON CONFLICT(key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """,
            (row["key"], row["value"], row["updated_at"]),
        )
        count += 1
    return count


def _copy_voice_files(sqlite_cursor, pg_cursor) -> int:
    if not _table_exists(sqlite_cursor, "voice_files"):
        return 0

    sqlite_columns = _sqlite_columns(sqlite_cursor, "voice_files")
    column_list = ["file_id", "user_id", "conversation_id", "message_id", "file_type", "storage_provider", "bucket", "object_key", "public_url", "content_type", "size_bytes", "status", "expires_at", "created_at", "updated_at"]
    selected_columns = [column for column in column_list if column in sqlite_columns]
    if not selected_columns:
        return 0

    sqlite_cursor.execute(
        f"SELECT {', '.join(selected_columns)} FROM voice_files ORDER BY id ASC"
    )
    rows = sqlite_cursor.fetchall()
    count = 0
    for row in rows:
        values = {column: row[column] for column in selected_columns}
        pg_cursor.execute(
            """
            INSERT INTO voice_files (
                file_id, user_id, conversation_id, message_id, file_type,
                storage_provider, bucket, object_key, public_url, content_type,
                size_bytes, status, expires_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, 'active'), %s, %s, %s)
            ON CONFLICT(file_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                conversation_id = EXCLUDED.conversation_id,
                message_id = EXCLUDED.message_id,
                file_type = EXCLUDED.file_type,
                storage_provider = EXCLUDED.storage_provider,
                bucket = EXCLUDED.bucket,
                object_key = EXCLUDED.object_key,
                public_url = EXCLUDED.public_url,
                content_type = EXCLUDED.content_type,
                size_bytes = EXCLUDED.size_bytes,
                status = EXCLUDED.status,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                values.get("file_id"),
                values.get("user_id"),
                values.get("conversation_id"),
                values.get("message_id"),
                values.get("file_type"),
                values.get("storage_provider"),
                values.get("bucket"),
                values.get("object_key"),
                values.get("public_url"),
                values.get("content_type"),
                values.get("size_bytes"),
                values.get("status"),
                values.get("expires_at"),
                values.get("created_at"),
                values.get("updated_at"),
            ),
        )
        count += 1
    return count


def migrate_sqlite_to_postgres(sqlite_path: Path, database_url: str, vector_dimension: int) -> dict[str, int]:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: psycopg. Install requirements before running migration.") from exc

    source_conn = _open_sqlite_connection(sqlite_path)
    try:
        with psycopg.connect(database_url) as pg_conn:
            with pg_conn.cursor() as pg_cursor:
                _ensure_schema(pg_cursor, vector_dimension)
            pg_conn.commit()

            with source_conn:
                sqlite_cursor = source_conn.cursor()
                with pg_conn.cursor() as pg_cursor:
                    users_count = _copy_users(sqlite_cursor, pg_cursor)
                    chat_messages_count, message_id_map = _copy_chat_messages(sqlite_cursor, pg_cursor)
                    counts = {
                        "users": users_count,
                        "chat_messages": chat_messages_count,
                        "conversations": _copy_conversations(sqlite_cursor, pg_cursor, message_id_map),
                        "user_memories": _copy_memories(sqlite_cursor, pg_cursor, message_id_map),
                        "memory_embeddings": _copy_memory_embeddings(
                            sqlite_cursor,
                            pg_cursor,
                            vector_dimension,
                        ),
                        "background_jobs": _copy_jobs(sqlite_cursor, pg_cursor),
                        "runtime_settings": _copy_runtime_settings(sqlite_cursor, pg_cursor),
                        "voice_files": _copy_voice_files(sqlite_cursor, pg_cursor),
                    }
                pg_conn.commit()
        return counts
    finally:
        source_conn.close()


def main() -> int:
    _load_dotenv_if_available()

    parser = argparse.ArgumentParser(description="Migrate Echo data from SQLite to PostgreSQL + pgvector.")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("ECHO_DB_PATH", str(PROJECT_ROOT / "data" / "echo_memory.db")),
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument(
        "--vector-dimension",
        type=int,
        default=int(os.getenv("EMBEDDING_VECTOR_DIMENSION", "1024")),
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required.")

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    counts = migrate_sqlite_to_postgres(sqlite_path, args.database_url, args.vector_dimension)
    print("Migration finished")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
