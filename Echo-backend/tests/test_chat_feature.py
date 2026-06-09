import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.entities import ChatContext, ChatValidationError, MemoryExtractionScheduleResult


class FakeConversationRepository:
    def __init__(self):
        self.persisted_turns = []

    def ensure_conversation(self, user_id, conversation_id):
        return conversation_id or "conv_fake"

    def get_or_create_active_conversation(self, user_id):
        return "conv_active"

    def add_chat_turn(
        self,
        user_id,
        conversation_id,
        user_message,
        assistant_reply,
        user_message_type,
        assistant_message_type,
    ):
        self.persisted_turns.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "user_message": user_message,
                "assistant_reply": assistant_reply,
                "user_message_type": user_message_type,
                "assistant_message_type": assistant_message_type,
            }
        )
        return 10, 11


class FakeContextProvider:
    async def build_context(self, user_id, user_message, conversation_id):
        return ChatContext(
            messages=[{"role": "user", "content": user_message}],
            history_messages=[],
        )


class FakeLLM:
    async def generate_reply(self, messages):
        return "你好，小安。"


class FakeSummaryUpdater:
    async def maybe_update_summary(self, user_id, conversation_id):
        return True


class FakeMemoryScheduler:
    def schedule(self, user_id, user_message, assistant_reply, source_message_id):
        return MemoryExtractionScheduleResult(
            should_extract=True,
            reason="keyword:以后",
            job_id="job_fake",
        )


class ChatFeatureTests(unittest.IsolatedAsyncioTestCase):
    def build_use_case(self):
        repository = FakeConversationRepository()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=FakeLLM(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )
        return use_case, repository

    async def test_generate_chat_reply_persists_turn_and_schedules_memory(self):
        use_case, repository = self.build_use_case()

        result = await use_case.execute(
            user_id=" user_a ",
            message=" 以后叫我小安吧 ",
        )

        self.assertEqual(result.reply, "你好，小安。")
        self.assertEqual(result.user_message, "以后叫我小安吧")
        self.assertEqual(result.conversation_id, "conv_active")
        self.assertEqual(result.user_message_id, 10)
        self.assertEqual(result.assistant_message_id, 11)
        self.assertTrue(result.summary_updated)
        self.assertTrue(result.memory_extraction_scheduled)
        self.assertEqual(result.memory_extraction_job_id, "job_fake")
        self.assertEqual(repository.persisted_turns[0]["user_message"], "以后叫我小安吧")

    async def test_generate_chat_reply_rejects_empty_message(self):
        use_case, _ = self.build_use_case()

        with self.assertRaises(ChatValidationError):
            await use_case.execute(user_id="user_a", message="   ")


if __name__ == "__main__":
    unittest.main()
