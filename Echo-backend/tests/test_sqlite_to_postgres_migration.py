import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_sqlite_to_postgres import _decode_embedding, _map_message_reference


class SQLiteToPostgresMigrationTests(unittest.TestCase):
    def test_embedding_json_is_decoded(self):
        self.assertEqual(_decode_embedding("[0.1, 0.2, 0.3]"), [0.1, 0.2, 0.3])

    def test_message_reference_is_remapped(self):
        message_id_map = {12: 108, 13: 109}

        self.assertEqual(_map_message_reference(message_id_map, 12), 108)
        self.assertEqual(_map_message_reference(message_id_map, 0), 0)
        self.assertIsNone(_map_message_reference(message_id_map, 99))
        self.assertIsNone(_map_message_reference(message_id_map, None))


if __name__ == "__main__":
    unittest.main()
