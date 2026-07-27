BEGIN;

ALTER TABLE user_personas
    ADD COLUMN IF NOT EXISTS relationship_pace VARCHAR(32) NOT NULL DEFAULT 'natural';

ALTER TABLE user_personas
    ADD COLUMN IF NOT EXISTS affection_style VARCHAR(32) NOT NULL DEFAULT 'contextual';

ALTER TABLE user_personas
    ALTER COLUMN schema_version SET DEFAULT 2;

UPDATE user_personas
SET schema_version = 2
WHERE schema_version < 2;

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
);

CREATE TABLE IF NOT EXISTS relationship_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    weight INTEGER NOT NULL DEFAULT 0,
    source_message_id BIGINT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relationship_states_stage
ON relationship_states(stage);

CREATE INDEX IF NOT EXISTS idx_relationship_states_updated_at
ON relationship_states(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_relationship_events_user_created
ON relationship_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_relationship_events_user_type
ON relationship_events(user_id, event_type);

COMMIT;
