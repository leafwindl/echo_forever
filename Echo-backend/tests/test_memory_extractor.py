import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.memory.public import parse_memory_extraction, should_extract_memory


class MemoryExtractorTests(unittest.TestCase):
    def test_gate_detects_memory_signal(self):
        result = should_extract_memory("以后叫我小安吧")

        self.assertTrue(result.should_extract)
        self.assertTrue(result.reason.startswith("keyword:"))

    def test_gate_skips_plain_chat(self):
        result = should_extract_memory("今天天气还不错")

        self.assertFalse(result.should_extract)
        self.assertEqual(result.reason, "no_memory_signal")

    def test_parse_json_wrapped_in_markdown_fence(self):
        memories = parse_memory_extraction(
            """```json
            {"memories":[{"action":"create","memory_type":"profile","content":"用户叫小安"}]}
            ```"""
        )

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["action"], "create")


if __name__ == "__main__":
    unittest.main()
