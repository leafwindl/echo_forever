import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.postgres_schema import build_postgres_schema_text


class PostgresSchemaTests(unittest.TestCase):
    def test_schema_contains_pgvector_memory_embedding(self):
        schema_text = build_postgres_schema_text(vector_dimension=1024)

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", schema_text)
        self.assertIn("embedding vector(1024) NOT NULL", schema_text)
        self.assertIn("CREATE TABLE IF NOT EXISTS memory_embeddings", schema_text)

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


if __name__ == "__main__":
    unittest.main()
