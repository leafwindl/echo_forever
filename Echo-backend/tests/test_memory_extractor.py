import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.memory.domain.extraction_rules import build_extraction_messages
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

    def test_gate_detects_semantic_identity_goal_and_relationship_preference(self):
        cases = (
            ("作为研究生，我最近开始看 Agent 论文", "semantic:identity"),
            ("我想做出一个更理解时间的 Echo", "semantic:goal"),
            ("我希望我们的交流是真诚和稳定的", "semantic:relationship_preference"),
        )

        for text, reason in cases:
            with self.subTest(text=text):
                result = should_extract_memory(text)
                self.assertTrue(result.should_extract)
                self.assertEqual(result.reason, reason)

    def test_periodic_batch_review_bypasses_narrow_realtime_gate(self):
        result = should_extract_memory("这句话没有固定关键词", force_batch_review=True)

        self.assertTrue(result.should_extract)
        self.assertEqual(result.reason, "periodic_batch_review")

    def test_extraction_prompt_requires_source_message_provenance(self):
        messages = build_extraction_messages(
            "- source_message_id=13 | 我想优化 Echo 的时间感知",
            "",
            [],
        )

        self.assertIn("source_message_id", messages[1]["content"])
        self.assertIn("只能来自“用户原话候选”", messages[1]["content"])

    def test_parse_json_wrapped_in_markdown_fence(self):
        memories = parse_memory_extraction("""```json
            {"memories":[{"action":"create","memory_type":"profile","content":"用户叫小安"}]}
            ```""")

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["action"], "create")


if __name__ == "__main__":
    unittest.main()
