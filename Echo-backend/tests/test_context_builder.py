import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.infrastructure.context_builder import _format_long_term_memories


class ContextBuilderTests(unittest.TestCase):
    def test_formats_memory_type_content_and_score(self):
        text = _format_long_term_memories([
            {
                "memory_type": "preference",
                "content": "用户喜欢安静的回复风格。",
                "similarity_score": 0.8765,
            }
        ])

        self.assertIn("[preference score=0.876]", text)
        self.assertIn("用户喜欢安静的回复风格。", text)


if __name__ == "__main__":
    unittest.main()
