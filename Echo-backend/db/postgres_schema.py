from __future__ import annotations

from shared.config import settings

from db.postgres_connection import transaction


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
        CREATE TABLE IF NOT EXISTS devices (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NOT NULL UNIQUE,
            client_id TEXT NOT NULL DEFAULT '',
            owner_user_id TEXT,
            display_name TEXT NOT NULL DEFAULT '我的 Echo',
            firmware_version TEXT NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'unclaimed'
                CHECK (status IN ('unclaimed', 'online', 'offline', 'revoked')),
            last_seen_at TIMESTAMPTZ,
            wifi_ssid TEXT NOT NULL DEFAULT '',
            bound_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS device_credentials (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            credential_hash TEXT NOT NULL UNIQUE,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'revoked')),
            issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS device_pairings (
            pairing_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            client_id TEXT NOT NULL DEFAULT '',
            code_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            claimed_at TIMESTAMPTZ,
            claimed_by_user_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS device_provisioning_sessions (
            session_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            device_id TEXT,
            client_id TEXT NOT NULL DEFAULT '',
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS speaker_people (
            person_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'collecting'
                CHECK (status IN ('collecting', 'verifying', 'active')),
            samples JSONB NOT NULL DEFAULT '[]'::jsonb,
            sample_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding JSONB NOT NULL DEFAULT '[]'::jsonb,
            model_id TEXT NOT NULL DEFAULT '',
            consented_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS speaker_device_calibrations (
            person_id TEXT PRIMARY KEY REFERENCES speaker_people(person_id) ON DELETE CASCADE,
            device_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            samples JSONB NOT NULL,
            embedding JSONB NOT NULL,
            verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        ALTER TABLE speaker_people
        ADD COLUMN IF NOT EXISTS sample_hashes JSONB NOT NULL DEFAULT '[]'::jsonb
        """,
        """
        CREATE TABLE IF NOT EXISTS speaker_profiles (
            id BIGSERIAL PRIMARY KEY,
            speaker_profile_id TEXT NOT NULL UNIQUE,
            owner_user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '主人',
            role VARCHAR(24) NOT NULL DEFAULT 'owner',
            embedding JSONB NOT NULL DEFAULT '[]'::jsonb,
            model_name TEXT NOT NULL DEFAULT 'echo-prototype-features',
            model_version TEXT NOT NULL DEFAULT '1',
            verification_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.78,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(owner_user_id, device_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS speaker_enrollment_samples (
            id BIGSERIAL PRIMARY KEY,
            speaker_profile_id TEXT NOT NULL,
            audio_duration_ms INTEGER NOT NULL DEFAULT 0,
            quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            embedding JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS device_voice_turns (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            user_id TEXT,
            request_id TEXT NOT NULL UNIQUE,
            user_message_id BIGINT,
            assistant_message_id BIGINT,
            speaker_profile_id TEXT,
            speaker_role VARCHAR(24) NOT NULL DEFAULT 'unknown',
            speaker_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            verification_status VARCHAR(24) NOT NULL DEFAULT 'unknown',
            asr_text TEXT NOT NULL DEFAULT '',
            audio_duration_ms INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGSERIAL PRIMARY KEY,
            message_id TEXT UNIQUE,
            client_message_id TEXT,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            message_type TEXT NOT NULL DEFAULT 'text',
            agent_turn_id TEXT,
            reply_group_id TEXT,
            sequence_in_group INTEGER NOT NULL DEFAULT 0,
            in_reply_to_message_id BIGINT,
            source TEXT,
            channel TEXT NOT NULL DEFAULT 'app_chat',
            visibility TEXT NOT NULL DEFAULT 'main_chat',
            status TEXT NOT NULL DEFAULT 'active',
            summarized_at TIMESTAMPTZ,
            delete_after TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS client_message_id TEXT",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS agent_turn_id TEXT",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reply_group_id TEXT",
        """
        ALTER TABLE chat_messages
        ADD COLUMN IF NOT EXISTS sequence_in_group INTEGER NOT NULL DEFAULT 0
        """,
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS in_reply_to_message_id BIGINT",
        """
        ALTER TABLE chat_messages
        ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'app_chat'
        """,
        """
        ALTER TABLE chat_messages
        ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'main_chat'
        """,
        """
        UPDATE chat_messages
        SET channel = 'device_voice', visibility = 'device_history'
        WHERE message_type IN ('voice_asr', 'voice_reply')
          AND channel = 'app_chat'
          AND visibility = 'main_chat'
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
            relationship_mode TEXT NOT NULL DEFAULT 'friend'
                CHECK (relationship_mode IN ('friend', 'ai_partner')),
            relationship_type VARCHAR(24) NOT NULL DEFAULT 'acquaintance'
                CHECK (relationship_type IN ('acquaintance', 'friend', 'ambiguous', 'partner')),
            relationship_type_updated_at TIMESTAMPTZ,
            reset_epoch BIGINT NOT NULL DEFAULT 0,
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
            schema_version INTEGER NOT NULL DEFAULT 2,
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
        """
        CREATE TABLE IF NOT EXISTS relationship_proposals (
            id BIGSERIAL PRIMARY KEY,
            proposal_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            direction VARCHAR(24) NOT NULL
                CHECK (direction IN ('friend', 'ambiguous', 'partner')),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'declined', 'deferred', 'expired', 'cancelled')),
            conversation_id TEXT,
            agent_turn_id TEXT,
            source_message_id BIGINT,
            evidence TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_relationship_proposals_pending_direction
        ON relationship_proposals(user_id, direction)
        WHERE status = 'pending'
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_relationship_proposals_user_status
        ON relationship_proposals(user_id, status, created_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS relationship_direction_boundaries (
            user_id TEXT NOT NULL,
            direction VARCHAR(24) NOT NULL
                CHECK (direction IN ('friend', 'ambiguous', 'partner')),
            status VARCHAR(16) NOT NULL
                CHECK (status IN ('declined', 'deferred')),
            reason TEXT NOT NULL DEFAULT '',
            source_message_id BIGINT,
            revisit_after TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, direction)
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
            status VARCHAR(32) NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'generating', 'retry_wait', 'ready_to_publish',
                    'ready', 'read', 'skipped', 'failed'
                )),
            subject TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            source_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_memory_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            generation_version TEXT NOT NULL,
            agent_run_id TEXT NOT NULL DEFAULT '',
            context_version TEXT NOT NULL DEFAULT '',
            context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            scheduled_at TIMESTAMPTZ,
            publish_at TIMESTAMPTZ,
            generated_at TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            read_at TIMESTAMPTZ,
            failure_code TEXT,
            reflection TEXT NOT NULL DEFAULT '',
            mood VARCHAR(80) NOT NULL DEFAULT '',
            image_brief JSONB NOT NULL DEFAULT '{}'::jsonb,
            image_storage_key TEXT NOT NULL DEFAULT '',
            image_content_type TEXT NOT NULL DEFAULT '',
            image_width INTEGER,
            image_height INTEGER,
            image_byte_size BIGINT,
            image_provider VARCHAR(64) NOT NULL DEFAULT '',
            image_model VARCHAR(128) NOT NULL DEFAULT '',
            image_reference_version VARCHAR(128) NOT NULL DEFAULT '',
            image_generation_status VARCHAR(32) NOT NULL DEFAULT 'disabled',
            image_failure_code TEXT,
            generation_attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            next_attempt_at TIMESTAMPTZ,
            lease_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, local_date, generation_version)
        )
        """,
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "source_memory_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "agent_run_id TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "context_version TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
        ),
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS publish_at TIMESTAMPTZ",
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS reflection TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS mood VARCHAR(80) NOT NULL DEFAULT ''",
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_brief JSONB NOT NULL DEFAULT '{}'::jsonb"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_storage_key TEXT NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_content_type TEXT NOT NULL DEFAULT ''"
        ),
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS image_width INTEGER",
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS image_height INTEGER",
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS image_byte_size BIGINT",
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_provider VARCHAR(64) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_model VARCHAR(128) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_reference_version VARCHAR(128) NOT NULL DEFAULT ''"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "image_generation_status VARCHAR(32) NOT NULL DEFAULT 'disabled'"
        ),
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS image_failure_code TEXT",
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "generation_attempt_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS "
            "max_attempts INTEGER NOT NULL DEFAULT 3"
        ),
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ",
        "ALTER TABLE daily_letters ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'daily_letters_status_check'
                  AND conrelid = 'daily_letters'::regclass
            ) THEN
                ALTER TABLE daily_letters
                    ADD CONSTRAINT daily_letters_status_check
                    CHECK (status IN (
                        'pending', 'generating', 'retry_wait', 'ready_to_publish',
                        'ready', 'read', 'skipped', 'failed'
                    )) NOT VALID;
            END IF;
        END $$
        """,
        "ALTER TABLE daily_letters VALIDATE CONSTRAINT daily_letters_status_check",
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
            priority INTEGER NOT NULL DEFAULT 100,
            description TEXT NOT NULL DEFAULT '',
            semantic_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'processing',
            moderation_status VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS sticker_embeddings (
            sticker_id TEXT PRIMARY KEY,
            embedding_model TEXT NOT NULL,
            semantic_text TEXT NOT NULL,
            embedding vector({dimension}) NOT NULL,
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
        """
        CREATE TABLE IF NOT EXISTS chat_turn_jobs (
            id BIGSERIAL PRIMARY KEY,
            turn_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'collecting'
                CHECK (status IN (
                    'collecting', 'queued', 'running', 'completed', 'failed', 'cancelled'
                )),
            input_first_message_id BIGINT NOT NULL,
            input_last_message_id BIGINT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 1 CHECK (message_count > 0),
            character_count INTEGER NOT NULL DEFAULT 0 CHECK (character_count >= 0),
            collect_until TIMESTAMPTZ NOT NULL,
            collect_deadline TIMESTAMPTZ NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 2 CHECK (max_attempts > 0),
            agent_run_id TEXT,
            reply_group_id TEXT,
            error_code TEXT,
            lease_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS proactive_chat_preferences (
            user_id TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            allow_echo_scheduling BOOLEAN NOT NULL DEFAULT TRUE,
            allow_spontaneous_chat BOOLEAN NOT NULL DEFAULT FALSE,
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            quiet_start TIME NOT NULL DEFAULT '22:30',
            quiet_end TIME NOT NULL DEFAULT '08:00',
            explicit_reminder_quiet_policy VARCHAR(16) NOT NULL DEFAULT 'defer'
                CHECK (explicit_reminder_quiet_policy IN ('honor', 'defer')),
            notification_preview BOOLEAN NOT NULL DEFAULT FALSE,
            cycle_started_at TIMESTAMPTZ,
            allowed_contact_seconds INTEGER NOT NULL DEFAULT 0,
            last_accounted_at TIMESTAMPTZ,
            last_evaluated_slot INTEGER NOT NULL DEFAULT 0,
            last_slot_result VARCHAR(16),
            paused_until TIMESTAMPTZ,
            pause_indefinite BOOLEAN NOT NULL DEFAULT FALSE,
            last_proactive_at TIMESTAMPTZ,
            consecutive_unanswered INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_schedules (
            id BIGSERIAL PRIMARY KEY,
            schedule_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            created_by VARCHAR(24) NOT NULL
                CHECK (created_by IN ('user_request', 'echo_agent', 'system_policy')),
            schedule_type VARCHAR(16) NOT NULL
                CHECK (schedule_type IN ('once', 'daily', 'weekly')),
            intent TEXT NOT NULL,
            user_visible_label TEXT NOT NULL DEFAULT '',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            next_run_at TIMESTAMPTZ NOT NULL,
            recurrence_rule JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
            run_count INTEGER NOT NULL DEFAULT 0,
            max_runs INTEGER,
            last_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS proactive_chat_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            schedule_id TEXT,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            scheduled_for TIMESTAMPTZ NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'succeeded', 'retry_wait', 'failed', 'suppressed', 'missed')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 2,
            lease_expires_at TIMESTAMPTZ,
            error_code TEXT,
            message_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(schedule_id, scheduled_for)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS push_targets (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            platform VARCHAR(24) NOT NULL,
            provider VARCHAR(24) NOT NULL DEFAULT 'getui',
            token TEXT NOT NULL,
            app_version TEXT NOT NULL DEFAULT '',
            environment TEXT NOT NULL DEFAULT '',
            locale TEXT NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_success_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, device_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notification_outbox (
            id BIGSERIAL PRIMARY KEY,
            notification_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            message_id TEXT,
            notification_type VARCHAR(32) NOT NULL,
            title TEXT NOT NULL DEFAULT 'Echo',
            body_policy VARCHAR(16) NOT NULL DEFAULT 'hidden',
            body TEXT NOT NULL DEFAULT '',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app_releases (
            id BIGSERIAL PRIMARY KEY,
            release_id TEXT NOT NULL UNIQUE,
            platform VARCHAR(24) NOT NULL,
            channel VARCHAR(32) NOT NULL,
            package_name TEXT NOT NULL,
            version_name VARCHAR(80) NOT NULL,
            version_code BIGINT NOT NULL CHECK (version_code > 0),
            minimum_version_code BIGINT NOT NULL DEFAULT 1
                CHECK (minimum_version_code > 0),
            cos_object_key TEXT NOT NULL,
            sha256 CHAR(64) NOT NULL,
            size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
            release_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
            mandatory BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(16) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'revoked')),
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(platform, channel, version_code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS desktop_nodes (
            id BIGSERIAL PRIMARY KEY,
            node_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            fingerprint TEXT NOT NULL DEFAULT '',
            token_hash CHAR(64) NOT NULL UNIQUE,
            capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'offline'
                CHECK (status IN ('online', 'offline', 'revoked')),
            last_seen_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS desktop_pairing_codes (
            id BIGSERIAL PRIMARY KEY,
            code_hash CHAR(64) NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS desktop_actions (
            id BIGSERIAL PRIMARY KEY,
            action_id TEXT NOT NULL UNIQUE,
            node_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status VARCHAR(16) NOT NULL
                CHECK (status IN ('running', 'completed', 'failed', 'timed_out', 'denied')),
            error_code TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mobile_agent_devices (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash CHAR(64) NOT NULL UNIQUE,
            status VARCHAR(16) NOT NULL DEFAULT 'offline'
                CHECK (status IN ('online', 'offline', 'revoked')),
            last_seen_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mobile_agent_actions (
            id BIGSERIAL PRIMARY KEY,
            action_id TEXT NOT NULL UNIQUE,
            device_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status VARCHAR(16) NOT NULL
                CHECK (status IN ('running', 'completed', 'failed', 'timed_out')),
            error_code TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mobile_agent_pairing_codes (
            id BIGSERIAL PRIMARY KEY,
            code_hash CHAR(64) NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS presence_states (
            user_id TEXT PRIMARY KEY,
            status VARCHAR(16) NOT NULL DEFAULT 'idle'
                CHECK (status IN ('active', 'idle', 'resting', 'sleeping', 'focused')),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_user_message_at TIMESTAMPTZ,
            last_tick_at TIMESTAMPTZ,
            last_thought_at TIMESTAMPTZ,
            thought_budget_date DATE,
            thoughts_used INTEGER NOT NULL DEFAULT 0 CHECK (thoughts_used >= 0),
            last_proactive_message_at TIMESTAMPTZ,
            proactive_messages_used INTEGER NOT NULL DEFAULT 0
                CHECK (proactive_messages_used >= 0),
            proactive_budget_date DATE,
            outreach_sent_count INTEGER NOT NULL DEFAULT 0
                CHECK (outreach_sent_count >= 0),
            outreach_replied_count INTEGER NOT NULL DEFAULT 0
                CHECK (outreach_replied_count >= 0),
            consecutive_unanswered INTEGER NOT NULL DEFAULT 0
                CHECK (consecutive_unanswered >= 0),
            outreach_downshift_until TIMESTAMPTZ,
            outreach_last_counted_at TIMESTAMPTZ,
            proactive_actions_used INTEGER NOT NULL DEFAULT 0
                CHECK (proactive_actions_used >= 0),
            proactive_action_budget_date DATE,
            last_proactive_action_at TIMESTAMPTZ,
            last_decision VARCHAR(24) NOT NULL DEFAULT '',
            last_decision_reason VARCHAR(64) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS presence_thoughts (
            id BIGSERIAL PRIMARY KEY,
            thought_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL,
            salience NUMERIC(4, 3) NOT NULL DEFAULT 0 CHECK (salience >= 0 AND salience <= 1),
            shareable BOOLEAN NOT NULL DEFAULT FALSE,
            action_intent TEXT NOT NULL DEFAULT '',
            source_memory_id TEXT NOT NULL DEFAULT '',
            source_memory_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS presence_events (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS firmware_releases (
            id BIGSERIAL PRIMARY KEY,
            release_id TEXT NOT NULL UNIQUE,
            board_type TEXT NOT NULL,
            board_variant TEXT NOT NULL DEFAULT '',
            version VARCHAR(80) NOT NULL,
            cos_object_key TEXT NOT NULL,
            sha256 CHAR(64) NOT NULL,
            size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
            release_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'revoked')),
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(board_type, board_variant, version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS study_focus_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            activity_type VARCHAR(40) NOT NULL DEFAULT '学习',
            short_goal VARCHAR(80) NOT NULL DEFAULT '',
            planned_duration_seconds INTEGER NOT NULL
                CHECK (planned_duration_seconds BETWEEN 60 AND 10800),
            actual_duration_seconds INTEGER NOT NULL DEFAULT 0
                CHECK (actual_duration_seconds BETWEEN 0 AND 10800),
            status VARCHAR(24) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'paused', 'completed', 'ended_early')),
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
            completion_message_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
        "CREATE INDEX IF NOT EXISTS idx_devices_owner_status ON devices(owner_user_id, status, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_device_credentials_device_status ON device_credentials(device_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_device_pairings_expires ON device_pairings(expires_at) WHERE claimed_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_device_provisioning_sessions_expires ON device_provisioning_sessions(expires_at) WHERE consumed_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_device_provisioning_sessions_owner ON device_provisioning_sessions(owner_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_speaker_profiles_owner_device ON speaker_profiles(owner_user_id, device_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_device_voice_turns_device_created ON device_voice_turns(device_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_status_updated
        ON conversations(user_id, status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_conversation_id
        ON chat_messages(user_id, conversation_id, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_main_chat_page
        ON chat_messages(user_id, conversation_id, visibility, id DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created ON chat_messages(user_id, created_at DESC)",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_user_client_message
        ON chat_messages(user_id, client_message_id)
        WHERE client_message_id IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_study_focus_user_started
        ON study_focus_sessions(user_id, started_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_study_focus_user_ended
        ON study_focus_sessions(user_id, ended_at DESC)
        WHERE ended_at IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_turn_group
        ON chat_messages(agent_turn_id, reply_group_id, sequence_in_group)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_turn_jobs_due
        ON chat_turn_jobs(status, collect_until, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chat_turn_jobs_user_conversation
        ON chat_turn_jobs(user_id, conversation_id, status, id)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_turn_jobs_one_running
        ON chat_turn_jobs(conversation_id)
        WHERE status = 'running'
        """,
        "CREATE INDEX IF NOT EXISTS idx_chat_schedules_user_status_next ON chat_schedules(user_id, status, next_run_at)",
        "CREATE INDEX IF NOT EXISTS idx_proactive_jobs_due ON proactive_chat_jobs(status, scheduled_for, id)",
        "CREATE INDEX IF NOT EXISTS idx_proactive_jobs_user ON proactive_chat_jobs(user_id, created_at DESC)",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS cycle_started_at TIMESTAMPTZ",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS allowed_contact_seconds INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS last_accounted_at TIMESTAMPTZ",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS last_evaluated_slot INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS last_slot_result VARCHAR(16)",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS paused_until TIMESTAMPTZ",
        "ALTER TABLE proactive_chat_preferences ADD COLUMN IF NOT EXISTS pause_indefinite BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE proactive_chat_preferences DROP COLUMN IF EXISTS proactivity_level",
        "ALTER TABLE proactive_chat_preferences DROP COLUMN IF EXISTS proactive_count",
        "ALTER TABLE proactive_chat_preferences DROP COLUMN IF EXISTS window_started_at",
        "ALTER TABLE push_targets ALTER COLUMN provider SET DEFAULT 'getui'",
        "CREATE INDEX IF NOT EXISTS idx_push_targets_user_status ON push_targets(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_notification_outbox_due ON notification_outbox(status, next_attempt_at, id)",
        "CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_memories_user_status ON user_memories(user_id, status)",
        """
        CREATE INDEX IF NOT EXISTS idx_user_memories_user_status_type
        ON user_memories(user_id, status, memory_type)
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_memories_source_message_id ON user_memories(source_message_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_personas_updated_at ON user_personas(updated_at DESC)",
        "ALTER TABLE relationship_states ADD COLUMN IF NOT EXISTS relationship_mode "
        "TEXT NOT NULL DEFAULT 'friend' CHECK (relationship_mode IN ('friend', 'ai_partner'))",
        "ALTER TABLE relationship_states ADD COLUMN IF NOT EXISTS relationship_type "
        "VARCHAR(24) NOT NULL DEFAULT 'acquaintance' "
        "CHECK (relationship_type IN ('acquaintance', 'friend', 'ambiguous', 'partner'))",
        "ALTER TABLE relationship_states ADD COLUMN IF NOT EXISTS relationship_type_updated_at TIMESTAMPTZ",
        "ALTER TABLE relationship_states ADD COLUMN IF NOT EXISTS reset_epoch BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE relationship_states ALTER COLUMN schema_version SET DEFAULT 2",
        "UPDATE relationship_states SET schema_version = 2 WHERE schema_version < 2",
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
        "CREATE INDEX IF NOT EXISTS idx_daily_letters_status_publish ON daily_letters(status, publish_at)",
        "CREATE INDEX IF NOT EXISTS idx_stickers_owner_status ON stickers(owner_user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_stickers_hash ON stickers(perceptual_hash)",
        """
        CREATE INDEX IF NOT EXISTS idx_sticker_embeddings_model
        ON sticker_embeddings(embedding_model)
        """,
        "ALTER TABLE stickers ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100",
        """
        CREATE INDEX IF NOT EXISTS idx_stickers_echo_priority
        ON stickers(owner_type, status, priority DESC, created_at DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_sticker_jobs_status_created ON sticker_generation_jobs(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_message_attachments(message_id, position)",
        "CREATE INDEX IF NOT EXISTS idx_chat_request_results_updated ON chat_request_results(status, updated_at)",
        """
        CREATE INDEX IF NOT EXISTS idx_app_releases_latest
        ON app_releases(platform, channel, version_code DESC)
        WHERE status='active'
        """,
        "ALTER TABLE desktop_nodes ADD COLUMN IF NOT EXISTS fingerprint TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS "
        "last_proactive_message_at TIMESTAMPTZ",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS proactive_messages_used "
        "INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS proactive_budget_date DATE",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS outreach_sent_count "
        "INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS outreach_replied_count "
        "INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS consecutive_unanswered "
        "INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS outreach_downshift_until "
        "TIMESTAMPTZ",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS outreach_last_counted_at "
        "TIMESTAMPTZ",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS proactive_actions_used "
        "INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS proactive_action_budget_date "
        "DATE",
        "ALTER TABLE presence_states ADD COLUMN IF NOT EXISTS last_proactive_action_at "
        "TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS idx_desktop_nodes_user_status "
        "ON desktop_nodes(user_id, status, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_desktop_pairing_codes_expires "
        "ON desktop_pairing_codes(expires_at) WHERE consumed_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_desktop_actions_user_created "
        "ON desktop_actions(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_mobile_agent_devices_user_status "
        "ON mobile_agent_devices(user_id, status, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_mobile_agent_pairing_expires "
        "ON mobile_agent_pairing_codes(expires_at) WHERE consumed_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_mobile_agent_actions_user_created "
        "ON mobile_agent_actions(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_presence_thoughts_user_created "
        "ON presence_thoughts(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_presence_events_user_created "
        "ON presence_events(user_id, created_at DESC)",
        """
        CREATE INDEX IF NOT EXISTS idx_firmware_releases_latest
        ON firmware_releases(board_type, board_variant, version DESC)
        WHERE status='active'
        """,
    ]


def build_postgres_schema_text(vector_dimension: int | None = None) -> str:
    return (
        ";\n\n".join(statement.strip() for statement in build_postgres_schema_sql(vector_dimension))
        + ";\n"
    )


def init_db() -> None:
    """Initialize the PostgreSQL + pgvector schema."""
    with transaction() as conn, conn.cursor() as cursor:
        for statement in build_postgres_schema_sql():
            cursor.execute(statement)
