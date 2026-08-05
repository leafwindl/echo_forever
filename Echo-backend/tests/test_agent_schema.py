import unittest

from db.postgres_schema import build_postgres_schema_text


class AgentSchemaTests(unittest.TestCase):
    def test_agent_letters_and_sticker_schema_is_present(self):
        schema = build_postgres_schema_text(3)
        self.assertIn("CREATE TABLE IF NOT EXISTS agent_runs", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS agent_tool_calls", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_letters", schema)
        self.assertIn("UNIQUE(user_id, local_date, generation_version)", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS stickers", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_message_attachments", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS chat_request_results", schema)
