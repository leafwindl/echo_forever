import sys
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.relationship.infrastructure.postgres_repository import _state_from_row


class RelationshipInfrastructureTests(unittest.TestCase):
    def test_postgres_row_is_converted_without_exposing_event_content(self):
        now = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
        state = _state_from_row(
            {
                "user_id": "user-a",
                "stage": "familiar",
                "score": 31,
                "interaction_turns": 20,
                "active_days": 4,
                "shared_memory_count": 3,
                "positive_signal_count": 1,
                "explicit_relation_signal_count": 0,
                "boundary_signal_count": 1,
                "affection_permission": "restrained",
                "last_interaction_date": date(2026, 7, 27),
                "last_interaction_at": now,
                "last_boundary_at": now,
                "stage_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "schema_version": 1,
            }
        )

        self.assertEqual("familiar", state.stage)
        self.assertEqual("2026-07-27", state.last_interaction_date)
        self.assertEqual(now.isoformat(), state.updated_at)
        self.assertEqual("restrained", state.affection_permission)


if __name__ == "__main__":
    unittest.main()
