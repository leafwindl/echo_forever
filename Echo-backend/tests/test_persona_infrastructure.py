import sys
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.persona.infrastructure.postgres_repository import (
    PostgresPersonaRepository,
    _persona_from_row,
)


class RecordingCursor:
    def __init__(self):
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return None


class RecordingConnection:
    def __init__(self, cursor):
        self.recording_cursor = cursor

    def cursor(self):
        return self.recording_cursor


class PersonaInfrastructureTests(unittest.TestCase):
    def test_get_query_is_always_scoped_to_requested_user(self):
        cursor = RecordingCursor()
        connection = RecordingConnection(cursor)

        @contextmanager
        def fake_connection():
            yield connection

        with patch(
            "features.persona.infrastructure.postgres_repository.get_connection",
            fake_connection,
        ):
            result = PostgresPersonaRepository().get("user-a")

        self.assertIsNone(result)
        self.assertIn("WHERE user_id = %s", cursor.query)
        self.assertEqual(("user-a",), cursor.params)

    def test_postgres_row_is_converted_to_domain_entity(self):
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        persona = _persona_from_row(
            {
                "user_id": "user-a",
                "preferred_name": "小叶",
                "reply_style": "concise",
                "reply_length": "short",
                "support_mode": "comfort",
                "proactivity": "quiet",
                "avoid_topics": '["家庭话题"]',
                "about_user": "喜欢直接交流",
                "enabled": True,
                "schema_version": 1,
                "created_at": now,
                "updated_at": now,
            }
        )

        self.assertEqual("user-a", persona.user_id)
        self.assertEqual(("家庭话题",), persona.avoid_topics)
        self.assertEqual(now.isoformat(), persona.created_at)
        self.assertTrue(persona.is_customized)

    def test_invalid_json_topics_degrade_to_empty_list(self):
        persona = _persona_from_row(
            {
                "user_id": "user-a",
                "preferred_name": None,
                "reply_style": "natural",
                "reply_length": "balanced",
                "support_mode": "balanced",
                "proactivity": "balanced",
                "avoid_topics": "not-json",
                "about_user": None,
                "enabled": False,
                "schema_version": 1,
                "created_at": None,
                "updated_at": None,
            }
        )

        self.assertEqual((), persona.avoid_topics)
        self.assertFalse(persona.enabled)


if __name__ == "__main__":
    unittest.main()
