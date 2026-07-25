from __future__ import annotations

from shared.config import settings


def build_postgres_schema_sql(vector_dimension: int | None = None) -> list[str]:
    """Build PostgreSQL + pgvector schema statements for the migration target."""
    dimension = vector_dimension or settings.embedding_vector_dimension
    if dimension <= 0:
        raise ValueError("Embedding vector dimension must be positive")

    return [
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE,
            openid TEXT UNIQUE,
            nickname TEXT,
            avatar_url TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id BIGSERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            title TEXT,
            summary TEXT NOT NULL DEFAULT '',
            summary_message_id BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGSERIAL PRIMARY KEY,
            message_id TEXT UNIQUE,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            message_type TEXT NOT NULL DEFAULT 'text',
            source TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            summarized_at TIMESTAMPTZ,
            delete_after TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_memories (
            id BIGSERIAL PRIMARY KEY,
            memory_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_message_id BIGINT,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.8,
            importance INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id BIGSERIAL PRIMARY KEY,
            memory_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding vector({dimension}) NOT NULL,
            vector_store_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS background_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payload JSONB NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS runtime_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'global',
            updated_by TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS voice_files (
            id BIGSERIAL PRIMARY KEY,
            file_id TEXT NOT NULL UNIQUE,
            user_id TEXT,
            conversation_id TEXT,
            message_id TEXT,
            file_type TEXT NOT NULL,
            storage_provider TEXT NOT NULL,
            bucket TEXT,
            object_key TEXT NOT NULL,
            public_url TEXT,
            content_type TEXT,
            size_bytes BIGINT,
            status TEXT NOT NULL DEFAULT 'active',
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_status_updated
        ON conversations(user_id, status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_conversation_id
        ON chat_messages(user_id, conversation_id, id)
        """,
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created ON chat_messages(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_memories_user_status ON user_memories(user_id, status)",
        """
        CREATE INDEX IF NOT EXISTS idx_user_memories_user_status_type
        ON user_memories(user_id, status, memory_type)
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_memories_source_message_id ON user_memories(source_message_id)",
        "CREATE INDEX IF NOT EXISTS idx_memory_embeddings_memory_id ON memory_embeddings(memory_id)",
        "CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user_id ON memory_embeddings(user_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user_model
        ON memory_embeddings(user_id, embedding_model)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_background_jobs_status_type
        ON background_jobs(status, job_type, id)
        """,
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_type_created ON background_jobs(job_type, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_runtime_settings_scope_key ON runtime_settings(scope, key)",
        "CREATE INDEX IF NOT EXISTS idx_voice_files_user_created ON voice_files(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_voice_files_status_expires ON voice_files(status, expires_at)",
    ]


def build_postgres_schema_text(vector_dimension: int | None = None) -> str:
    return ";\n\n".join(statement.strip() for statement in build_postgres_schema_sql(vector_dimension)) + ";\n"
