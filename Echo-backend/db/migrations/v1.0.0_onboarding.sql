BEGIN;

ALTER TABLE user_personas
    ADD COLUMN IF NOT EXISTS is_customized BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE user_personas
    ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE user_personas
    ALTER COLUMN schema_version SET DEFAULT 3;

UPDATE user_personas
SET schema_version = 3
WHERE schema_version < 3;

COMMIT;
