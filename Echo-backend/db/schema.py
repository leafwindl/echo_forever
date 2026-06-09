import sqlite3

from db.connection import transaction


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column_if_missing(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """初始化数据库，并执行不会删除旧数据的表结构迁移。"""
    with transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                openid TEXT UNIQUE,
                nickname TEXT,
                avatar_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                title TEXT,
                summary TEXT DEFAULT '',
                summary_message_id INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _add_column_if_missing(cursor, "conversations", "summary_message_id", "INTEGER DEFAULT 0")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                conversation_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _add_column_if_missing(cursor, "chat_messages", "conversation_id", "TEXT")
        _add_column_if_missing(cursor, "chat_messages", "message_type", "TEXT DEFAULT 'text'")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source_message_id INTEGER,
                confidence REAL DEFAULT 0.8,
                importance INTEGER DEFAULT 3,
                status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL UNIQUE,
                user_id TEXT,
                embedding_model TEXT NOT NULL,
                embedding TEXT,
                vector_store_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _add_column_if_missing(cursor, "memory_embeddings", "user_id", "TEXT")
        _add_column_if_missing(cursor, "memory_embeddings", "embedding", "TEXT")
        _add_column_if_missing(cursor, "memory_embeddings", "updated_at", "DATETIME")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME
            )
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_user_conversation_id
            ON chat_messages(user_id, conversation_id, id)
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_memories_user_status
            ON user_memories(user_id, status)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_memories_user_status_type
            ON user_memories(user_id, status, memory_type)
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_embeddings_memory_id ON memory_embeddings(memory_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user_id ON memory_embeddings(user_id)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_background_jobs_status_type
            ON background_jobs(status, job_type, id)
            """
        )
