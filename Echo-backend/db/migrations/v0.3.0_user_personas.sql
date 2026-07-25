-- Echo PostgreSQL schema migration: v0.3.0-user-personas-1
-- Forward migration is idempotent. Rollback is intentionally manual because it deletes user data.

BEGIN;

CREATE TABLE IF NOT EXISTS user_personas (
    user_id TEXT PRIMARY KEY,
    preferred_name VARCHAR(40),
    reply_style VARCHAR(32) NOT NULL DEFAULT 'natural',
    reply_length VARCHAR(32) NOT NULL DEFAULT 'balanced',
    support_mode VARCHAR(32) NOT NULL DEFAULT 'balanced',
    proactivity VARCHAR(32) NOT NULL DEFAULT 'balanced',
    avoid_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    about_user VARCHAR(300),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_personas_updated_at
ON user_personas(updated_at DESC);

COMMIT;
