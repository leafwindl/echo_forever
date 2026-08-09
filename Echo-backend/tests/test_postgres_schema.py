import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.postgres_schema import build_postgres_schema_sql, build_postgres_schema_text


class PostgresSchemaTests(unittest.TestCase):
    def test_schema_contains_pgvector_memory_embedding(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", schema_text)
        self.assertIn("embedding vector(1024) NOT NULL", schema_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS memory_embeddings", schema_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS sticker_embeddings", schema_text)
        self.assertIn("semantic_text TEXT NOT NULL", schema_text)

    def test_schema_contains_chat_lifecycle_and_voice_files(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("status TEXT NOT NULL DEFAULT 'active'", schema_text)
        self.assertIn("summarized_at TIMESTAMPTZ", schema_text)
        self.assertIn("delete_after TIMESTAMPTZ", schema_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS voice_files", schema_text)
        self.assertIn("storage_provider TEXT NOT NULL", schema_text)

    def test_schema_contains_user_persona_settings(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("CREATE TABLE IF NOT EXISTS user_personas", schema_text)
        self.assertIn("user_id TEXT PRIMARY KEY", schema_text)
        self.assertIn("avoid_topics JSONB NOT NULL", schema_text)
        self.assertIn("relationship_pace VARCHAR(32) NOT NULL DEFAULT 'natural'", schema_text)
        self.assertIn("affection_style VARCHAR(32) NOT NULL DEFAULT 'contextual'", schema_text)
        self.assertIn("is_customized BOOLEAN NOT NULL DEFAULT TRUE", schema_text)
        self.assertIn("onboarding_completed BOOLEAN NOT NULL DEFAULT TRUE", schema_text)
        self.assertIn("schema_version INTEGER NOT NULL DEFAULT 3", schema_text)

    def test_schema_contains_relationship_state_and_event_log(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("CREATE TABLE IF NOT EXISTS relationship_states", schema_text)
        self.assertIn("affection_permission VARCHAR(32)", schema_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS relationship_events", schema_text)
        self.assertIn("idx_relationship_events_user_type", schema_text)

    def test_phone_auth_upgrade_alters_legacy_users_before_creating_index(self):
        statements = [
            statement.strip() for statement in build_postgres_schema_sql(vector_dimension=1024)
        ]

        drop_openid = statements.index("ALTER TABLE users DROP COLUMN IF EXISTS openid")
        add_phone = statements.index("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT")
        add_phone_verified_at = statements.index(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ"
        )
        create_phone_index = statements.index(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL"
        )

        self.assertLess(drop_openid, add_phone)
        self.assertLess(add_phone, create_phone_index)
        self.assertLess(add_phone_verified_at, create_phone_index)

    def test_schema_contains_direct_app_releases(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("CREATE TABLE IF NOT EXISTS app_releases", schema_text)
        self.assertIn("UNIQUE(platform, channel, version_code)", schema_text)
        self.assertIn("idx_app_releases_latest", schema_text)


if __name__ == "__main__":
    unittest.main()
