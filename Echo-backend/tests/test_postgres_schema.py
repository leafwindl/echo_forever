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


if __name__ == "__main__":
    unittest.main()
