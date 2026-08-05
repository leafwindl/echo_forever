from __future__ import annotations

from db.postgres_connection import transaction
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
            phone TEXT UNIQUE,
            phone_verified_at TIMESTAMPTZ,
            nickname TEXT,
            avatar_url TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "DROP INDEX IF EXISTS idx_users_openid",
        "ALTER TABLE users DROP COLUMN IF EXISTS openid",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ",
        """
        CREATE TABLE IF NOT EXISTS sms_verification_challenges (
            request_id TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            purpose VARCHAR(32) NOT NULL CHECK (purpose = 'login'),
            device_id TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
            token_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            token_family_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            replaced_by TEXT,
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
        CREATE TABLE IF NOT EXISTS chat_request_results (
            user_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'processing',
            response_payload JSONB,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, request_id)
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
        """
        CREATE TABLE IF NOT EXISTS user_personas (
            user_id TEXT PRIMARY KEY,
            preferred_name VARCHAR(40),
            reply_style VARCHAR(32) NOT NULL DEFAULT 'natural',
            reply_length VARCHAR(32) NOT NULL DEFAULT 'balanced',
            support_mode VARCHAR(32) NOT NULL DEFAULT 'balanced',
            proactivity VARCHAR(32) NOT NULL DEFAULT 'balanced',
            avoid_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
            about_user VARCHAR(300),
            relationship_pace VARCHAR(32) NOT NULL DEFAULT 'natural',
            affection_style VARCHAR(32) NOT NULL DEFAULT 'contextual',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            is_customized BOOLEAN NOT NULL DEFAULT TRUE,
            onboarding_completed BOOLEAN NOT NULL DEFAULT TRUE,
            schema_version INTEGER NOT NULL DEFAULT 3,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationship_states (
            user_id TEXT PRIMARY KEY,
            stage VARCHAR(32) NOT NULL DEFAULT 'new',
            score INTEGER NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
            interaction_turns INTEGER NOT NULL DEFAULT 0 CHECK (interaction_turns >= 0),
            active_days INTEGER NOT NULL DEFAULT 0 CHECK (active_days >= 0),
            shared_memory_count INTEGER NOT NULL DEFAULT 0 CHECK (shared_memory_count >= 0),
            positive_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (positive_signal_count >= 0),
            explicit_relation_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (explicit_relation_signal_count >= 0),
            boundary_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (boundary_signal_count >= 0),
            affection_permission VARCHAR(32) NOT NULL DEFAULT 'unknown',
            last_interaction_date DATE,
            last_interaction_at TIMESTAMPTZ,
            last_boundary_at TIMESTAMPTZ,
            stage_updated_at TIMESTAMPTZ,
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationship_events (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            weight INTEGER NOT NULL DEFAULT 0,
            source_message_id BIGINT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            trigger_type VARCHAR(32) NOT NULL,
            trigger_id TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            objective TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            max_steps INTEGER NOT NULL DEFAULT 6,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_tool_calls (
            id BIGSERIAL PRIMARY KEY,
            tool_call_id TEXT NOT NULL UNIQUE,
            run_id TEXT NOT NULL,
            tool_name VARCHAR(80) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS daily_letters (
            id BIGSERIAL PRIMARY KEY,
            letter_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            local_date DATE NOT NULL,
            timezone TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            subject TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            source_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            generation_version TEXT NOT NULL,
            scheduled_at TIMESTAMPTZ,
            generated_at TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            read_at TIMESTAMPTZ,
            failure_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, local_date, generation_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS letter_preferences (
            user_id TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            publish_time TIME NOT NULL DEFAULT '08:00',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stickers (
            id BIGSERIAL PRIMARY KEY,
            sticker_id TEXT NOT NULL UNIQUE,
            owner_type VARCHAR(16) NOT NULL,
            owner_user_id TEXT,
            source VARCHAR(16) NOT NULL,
            storage_key TEXT NOT NULL,
            public_url TEXT,
            content_type TEXT NOT NULL,
            width INTEGER,
            height INTEGER,
            byte_size BIGINT NOT NULL DEFAULT 0,
            perceptual_hash TEXT,
            description TEXT NOT NULL DEFAULT '',
            semantic_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'processing',
            moderation_status VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sticker_generation_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            normalized_intent TEXT NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            generated_sticker_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_message_attachments (
            id BIGSERIAL PRIMARY KEY,
            attachment_id TEXT NOT NULL UNIQUE,
            message_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            attachment_type VARCHAR(24) NOT NULL,
            resource_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL",
        """
        CREATE INDEX IF NOT EXISTS idx_sms_challenges_phone_created
        ON sms_verification_challenges(phone, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sms_challenges_device_created
        ON sms_verification_challenges(device_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sms_challenges_expires
        ON sms_verification_challenges(expires_at)
        WHERE consumed_at IS NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_family
        ON auth_refresh_tokens(token_family_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_device
        ON auth_refresh_tokens(user_id, device_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
        ON auth_refresh_tokens(expires_at)
        WHERE revoked_at IS NULL
        """,
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
        "CREATE INDEX IF NOT EXISTS idx_user_personas_updated_at ON user_personas(updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_relationship_states_stage ON relationship_states(stage)",
        "CREATE INDEX IF NOT EXISTS idx_relationship_states_updated_at ON relationship_states(updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_relationship_events_user_created ON relationship_events(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_relationship_events_user_type ON relationship_events(user_id, event_type)",
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
        "CREATE INDEX IF NOT EXISTS idx_voice_files_user_created ON voice_files(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_voice_files_status_expires ON voice_files(status, expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_user_created ON agent_runs(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON agent_runs(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run_created ON agent_tool_calls(run_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_daily_letters_user_published ON daily_letters(user_id, published_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_daily_letters_status_scheduled ON daily_letters(status, scheduled_at)",
        "CREATE INDEX IF NOT EXISTS idx_stickers_owner_status ON stickers(owner_user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_stickers_hash ON stickers(perceptual_hash)",
        "CREATE INDEX IF NOT EXISTS idx_sticker_jobs_status_created ON sticker_generation_jobs(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_message_attachments(message_id, position)",
        "CREATE INDEX IF NOT EXISTS idx_chat_request_results_updated ON chat_request_results(status, updated_at)",
    ]


def build_postgres_schema_text(vector_dimension: int | None = None) -> str:
    return (
        ";\n\n".join(statement.strip() for statement in build_postgres_schema_sql(vector_dimension))
        + ";\n"
    )


def init_db() -> None:
    """Initialize the PostgreSQL + pgvector schema."""
    with transaction() as conn:
        with conn.cursor() as cursor:
            for statement in build_postgres_schema_sql():
                cursor.execute(statement)
