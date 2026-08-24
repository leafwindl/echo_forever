import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.infrastructure import postgres_repositories


class _FakeCursor:
    def __init__(self, rows=None):
        self.calls: list[tuple[str, tuple | None]] = []
        self.rows = list(rows or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return {"id": 42}

    def fetchall(self):
        rows = self.rows
        self.rows = []
        return rows


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class ChatPostgresRepositoryTests(unittest.TestCase):
    def test_any_persisted_user_message_resets_proactive_unanswered_count(self):
        cursor = _FakeCursor()

        with patch.object(postgres_repositories, "ensure_user_identity"):
            postgres_repositories._add_message_record(
                user_id="user-a",
                role="user",
                content="你好，Echo",
                conversation_id=None,
                message_type="voice_asr",
                conn=_FakeConnection(cursor),
            )

        reset_calls = [
            (query, params)
            for query, params in cursor.calls
            if "SET consecutive_unanswered = 0" in query
        ]
        self.assertEqual(1, len(reset_calls))
        self.assertEqual(("user-a",), reset_calls[0][1])

    def test_assistant_message_does_not_reset_proactive_unanswered_count(self):
        cursor = _FakeCursor()

        with patch.object(postgres_repositories, "ensure_user_identity"):
            postgres_repositories._add_message_record(
                user_id="user-a",
                role="assistant",
                content="我在。",
                conversation_id=None,
                message_type="voice_reply",
                conn=_FakeConnection(cursor),
            )

        self.assertFalse(
            any("SET consecutive_unanswered = 0" in query for query, _ in cursor.calls)
        )

    def test_main_chat_page_filters_visibility_before_pagination(self):
        cursor = _FakeCursor()
        connection = _FakeConnection(cursor)

        with patch.object(postgres_repositories, "get_connection", return_value=connection):
            rows, has_more = postgres_repositories.list_messages_page(
                "user-a",
                "conv-a",
                before_id=None,
                after_id=None,
                limit=10,
            )

        self.assertEqual(rows, [])
        self.assertFalse(has_more)
        page_query = next(query for query, _ in cursor.calls if "FROM chat_messages" in query)
        self.assertIn("visibility = 'main_chat'", page_query)


if __name__ == "__main__":
    unittest.main()
