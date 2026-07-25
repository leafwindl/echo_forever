import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.memory.infrastructure.adapters import _memory_from_record


class MemoryInfrastructureAdapterTests(unittest.TestCase):
    def test_postgres_datetimes_are_converted_to_iso_strings(self):
        created_at = datetime(2026, 7, 11, 8, 30, tzinfo=timezone.utc)
        record = {
            "memory_id": "mem_test",
            "user_id": "user_test",
            "memory_type": "preference",
            "content": "用户喜欢简洁回复",
            "source_message_id": 12,
            "confidence": 0.9,
            "importance": 4,
            "status": "active",
            "created_at": created_at,
            "updated_at": "2026-07-11T09:00:00+00:00",
            "expires_at": None,
        }

        memory = _memory_from_record(record)

        self.assertEqual(memory.created_at, "2026-07-11T08:30:00+00:00")
        self.assertEqual(memory.updated_at, "2026-07-11T09:00:00+00:00")
        self.assertIsNone(memory.expires_at)


if __name__ == "__main__":
    unittest.main()
