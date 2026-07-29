import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.infrastructure import conversation_summary


class FakeSummaryLLM:
    def __init__(self):
        self.calls = []

    async def chat_completion(self, messages, **options):
        self.calls.append((messages, options))
        return (
            "[USER_FACTS]\n"
            "- source_message_id=1 | 用户是研究生。\n"
            "[/USER_FACTS]\n"
            "[DORMANT_TOPICS]\n[/DORMANT_TOPICS]"
        )


class ConversationSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_uses_provenance_prompt_and_dedicated_generation_budget(self):
        provider = FakeSummaryLLM()
        messages = [
            {"id": 1, "role": "user", "content": "我是研究生"},
            {"id": 2, "role": "assistant", "content": "你一定每天都在实验室"},
        ] * 13

        with (
            patch.object(
                conversation_summary.postgres_repositories,
                "get_conversation_summary",
                return_value={"summary": "", "summary_message_id": 0},
            ),
            patch.object(
                conversation_summary.postgres_repositories,
                "get_conversation_messages",
                return_value=messages,
            ),
            patch.object(
                conversation_summary.postgres_repositories,
                "update_conversation_summary",
            ) as update_summary,
            patch.object(conversation_summary, "get_llm_provider", return_value=provider),
            patch.object(
                conversation_summary.settings, "conversation_summary_trigger_messages", 24
            ),
            patch.object(
                conversation_summary.settings, "conversation_summary_keep_recent_messages", 12
            ),
            patch.object(conversation_summary.settings, "conversation_summary_temperature", 0.1),
            patch.object(conversation_summary.settings, "conversation_summary_max_tokens", 1200),
        ):
            updated = await conversation_summary.maybe_update_conversation_summary(
                "user-a",
                "conv-a",
            )

        self.assertTrue(updated)
        prompt = provider.calls[0][0][1]["content"]
        self.assertIn("message_id=1 role=user", prompt)
        self.assertIn("role=assistant 只用于理解指代", prompt)
        self.assertIn("DORMANT_TOPICS", prompt)
        self.assertEqual(
            provider.calls[0][1],
            {"temperature": 0.1, "max_tokens": 1200},
        )
        update_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
