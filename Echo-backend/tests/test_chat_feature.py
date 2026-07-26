import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.send_message import SendChatMessage
from features.chat.domain.entities import (
    ChatContext,
    ChatRequestInProgressError,
    ChatValidationError,
    MemoryExtractionScheduleResult,
)


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
        return "hello from echo"


class SequenceLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def generate_reply(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


class FakeSummaryUpdater:
    async def maybe_update_summary(self, user_id, conversation_id):
        return True


class FakeMemoryScheduler:
    def schedule(self, user_id, user_message, assistant_reply, source_message_id):
        return MemoryExtractionScheduleResult(
            should_extract=True,
            reason="keyword:test",
            job_id="job_fake",
        )


class FakeVoiceReplySynthesizer:
    def __init__(self):
        self.received_replies = []

    async def synthesize_reply(self, reply):
        self.received_replies.append(reply)
        return "http://example.test/voice.mp3"


class FailingVoiceReplySynthesizer:
    async def synthesize_reply(self, reply):
        raise RuntimeError(f"tts failed:{reply}")


class FakeChatRequestGuard:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.try_calls = []
        self.release_calls = []

    def try_acquire(self, user_id):
        self.try_calls.append(user_id)
        return self.acquired

    def release(self, user_id):
        self.release_calls.append(user_id)


class ChatFeatureTests(unittest.IsolatedAsyncioTestCase):
    def build_generate_use_case(self):
        repository = FakeConversationRepository()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=FakeLLM(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )
        return use_case, repository

    def build_send_use_case(self, voice_synthesizer=None, request_guard=None):
        chat_reply_generator, repository = self.build_generate_use_case()
        use_case = SendChatMessage(
            chat_reply_generator=chat_reply_generator,
            voice_reply_synthesizer=voice_synthesizer or FakeVoiceReplySynthesizer(),
            request_guard=request_guard or FakeChatRequestGuard(),
        )
        return use_case, repository

    async def test_generate_chat_reply_persists_turn_and_schedules_memory(self):
        use_case, repository = self.build_generate_use_case()

        result = await use_case.execute(
            user_id=" user_a ",
            message=" remember my name ",
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertEqual(result.user_message, "remember my name")
        self.assertEqual(result.conversation_id, "conv_active")
        self.assertEqual(result.user_message_id, 10)
        self.assertEqual(result.assistant_message_id, 11)
        self.assertTrue(result.summary_updated)
        self.assertTrue(result.memory_extraction_scheduled)
        self.assertEqual(result.memory_extraction_job_id, "job_fake")
        self.assertEqual(repository.persisted_turns[0]["user_message"], "remember my name")

    async def test_generate_chat_reply_rejects_empty_message(self):
        use_case, _ = self.build_generate_use_case()

        with self.assertRaises(ChatValidationError):
            await use_case.execute(user_id="user_a", message="   ")

    async def test_generate_chat_reply_retries_stage_direction_once(self):
        repository = FakeConversationRepository()
        llm = SequenceLLM(["（轻轻抱住你）别难过。", "听起来你真的很难受，我在这里听你说。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=llm,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )

        result = await use_case.execute(user_id="user_a", message="我今天很难过")

        self.assertEqual("听起来你真的很难受，我在这里听你说。", result.reply)
        self.assertEqual(2, len(llm.calls))
        self.assertIn("只输出直接对用户说的话", llm.calls[1][-1]["content"])
        self.assertEqual(result.reply, repository.persisted_turns[0]["assistant_reply"])

    async def test_generate_chat_reply_sanitizes_second_style_violation(self):
        repository = FakeConversationRepository()
        llm = SequenceLLM(["*拍拍你* 会好起来的。", "Echo：［轻轻点头］我会认真听。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=llm,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )

        result = await use_case.execute(user_id="user_a", message="陪我说说话")

        self.assertEqual("我会认真听。", result.reply)
        self.assertEqual(2, len(llm.calls))

    async def test_send_chat_message_can_return_voice_reply_url(self):
        voice_synthesizer = FakeVoiceReplySynthesizer()
        use_case, repository = self.build_send_use_case(voice_synthesizer=voice_synthesizer)

        result = await use_case.execute(
            user_id="user_a",
            message="hello",
            input_type="voice",
            voice_reply_enabled=True,
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertEqual(result.audio_url, "http://example.test/voice.mp3")
        self.assertEqual(result.audio_urls, ("http://example.test/voice.mp3",))
        self.assertEqual(voice_synthesizer.received_replies, ["hello from echo"])
        self.assertEqual(repository.persisted_turns[0]["user_message_type"], "voice_asr")
        self.assertEqual(repository.persisted_turns[0]["assistant_message_type"], "voice_reply")

    async def test_send_chat_message_keeps_text_reply_when_voice_synthesis_fails(self):
        use_case, _ = self.build_send_use_case(voice_synthesizer=FailingVoiceReplySynthesizer())

        result = await use_case.execute(
            user_id="user_a",
            message="hello",
            voice_reply_enabled=True,
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertIsNone(result.audio_url)

    async def test_send_chat_message_rejects_when_user_request_is_in_progress(self):
        request_guard = FakeChatRequestGuard(acquired=False)
        use_case, _ = self.build_send_use_case(request_guard=request_guard)

        with self.assertRaises(ChatRequestInProgressError):
            await use_case.execute(user_id=" user_a ", message="hello")

        self.assertEqual(request_guard.try_calls, ["user_a"])
        self.assertEqual(request_guard.release_calls, [])

    async def test_send_chat_message_releases_guard_after_success(self):
        request_guard = FakeChatRequestGuard()
        use_case, _ = self.build_send_use_case(request_guard=request_guard)

        await use_case.execute(user_id=" user_a ", message="hello")

        self.assertEqual(request_guard.try_calls, ["user_a"])
        self.assertEqual(request_guard.release_calls, ["user_a"])


if __name__ == "__main__":
    unittest.main()
