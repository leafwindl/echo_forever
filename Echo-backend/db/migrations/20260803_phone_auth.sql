BEGIN;

DROP INDEX IF EXISTS idx_users_openid;
ALTER TABLE users DROP COLUMN IF EXISTS openid;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone
    ON users(phone) WHERE phone IS NOT NULL;

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
);

CREATE INDEX IF NOT EXISTS idx_sms_challenges_phone_created
    ON sms_verification_challenges(phone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sms_challenges_device_created
    ON sms_verification_challenges(device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sms_challenges_expires
    ON sms_verification_challenges(expires_at) WHERE consumed_at IS NULL;

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
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_family
    ON auth_refresh_tokens(token_family_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_device
    ON auth_refresh_tokens(user_id, device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
    ON auth_refresh_tokens(expires_at) WHERE revoked_at IS NULL;

COMMIT;
