import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.application.clear_context import ClearChatContext
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.send_message import SendChatMessage
from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.domain.entities import (
    ChatContext,
    ChatRequestInProgressError,
    ChatValidationError,
    MemoryExtractionScheduleResult,
)


class FakeConversationRepository:
    def __init__(self):
        self.persisted_turns = []
        self.cleared_user_ids = []

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

    def clear_context(self, user_id):
        self.cleared_user_ids.append(user_id)
        return 4, 1


class FakeContextProvider:
    def __init__(self):
        self.conversation_modes = []

    async def build_context(self, user_id, user_message, conversation_id, conversation_mode):
        self.conversation_modes.append(conversation_mode)
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


class BlockingSummaryUpdater:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def maybe_update_summary(self, user_id, conversation_id):
        self.started.set()
        await self.release.wait()
        return True


class FakeMemoryScheduler:
    def schedule(self, user_id, user_message, assistant_reply, source_message_id):
        return MemoryExtractionScheduleResult(
            should_extract=True,
            reason="keyword:test",
            job_id="job_fake",
        )


class FakeRelationshipRecorder:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def record(self, user_id, user_message, source_message_id):
        self.calls.append((user_id, user_message, source_message_id))
        return self.result


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
    async def test_clear_chat_context_uses_clean_authenticated_user_id(self):
        repository = FakeConversationRepository()
        result = ClearChatContext(repository).execute(" user_a ")

        self.assertEqual(repository.cleared_user_ids, ["user_a"])
        self.assertEqual(result.deleted_messages, 4)
        self.assertEqual(result.reset_conversations, 1)

    def build_generate_use_case(self):
        repository = FakeConversationRepository()
        relationship_recorder = FakeRelationshipRecorder()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=FakeLLM(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            relationship_recorder=relationship_recorder,
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

    async def test_generate_chat_reply_records_relationship_after_persisting_turn(self):
        repository = FakeConversationRepository()
        recorder = FakeRelationshipRecorder()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=FakeLLM(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            relationship_recorder=recorder,
        )

        await use_case.execute(user_id="user_a", message="今天赢球了")

        self.assertEqual([("user_a", "今天赢球了", 10)], recorder.calls)

    async def test_generate_chat_reply_rejects_empty_message(self):
        use_case, _ = self.build_generate_use_case()

        with self.assertRaises(ChatValidationError):
            await use_case.execute(user_id="user_a", message="   ")

    async def test_generate_chat_reply_can_update_summary_in_background(self):
        summary_updater = BlockingSummaryUpdater()
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=FakeContextProvider(),
            llm=FakeLLM(),
            summary_updater=summary_updater,
            memory_scheduler=FakeMemoryScheduler(),
            summary_update_in_background=True,
        )

        result = await asyncio.wait_for(
            use_case.execute(user_id="user_a", message="hello"),
            timeout=0.1,
        )

        self.assertFalse(result.summary_updated)
        await asyncio.wait_for(summary_updater.started.wait(), timeout=0.1)
        summary_updater.release.set()
        await asyncio.sleep(0)

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

    def test_dialogue_style_flags_contextual_naturalness_violations(self):
        self.assertIn(
            "fabricated_offline_state",
            find_dialogue_style_violations("不忙，刚看完几篇文章。", "你在忙吗？"),
        )
        self.assertIn(
            "fabricated_human_experience",
            find_dialogue_style_violations("我也经常累了就躺着。", "今天有点累。"),
        )
        self.assertIn(
            "direct_physical_action",
            find_dialogue_style_violations("抱抱你，我在。", "今天很难过。"),
        )
        self.assertIn(
            "unrequested_advice",
            find_dialogue_style_violations("累了就歇会儿，别硬撑。", "今天有点累。"),
        )
        self.assertIn(
            "unrequested_advice",
            find_dialogue_style_violations("听起来消耗不少，歇一歇吧。", "今天有点累。"),
        )
        self.assertIn(
            "unrequested_advice",
            find_dialogue_style_violations("明白，先缓缓也行。", "我不想听建议。"),
        )
        self.assertIn(
            "multiple_questions",
            find_dialogue_style_violations("跟谁打的？比分怎么样？", "今天赢球了。"),
        )
        self.assertIn(
            "ungrounded_time_detail",
            find_dialogue_style_violations("今天周六也累到了？", "今天有点累。"),
        )

    def test_dialogue_style_flags_unverified_voice_capabilities(self):
        violations = find_dialogue_style_violations(
            "我会把声音调整成熟一点，你可以去设置里选择其他音色选项。",
            "声音可以成熟一点吗？",
        )

        self.assertIn("voice_capability_promise", violations)
        self.assertIn("unverified_settings", violations)
        self.assertIn(
            "unverified_settings",
            find_dialogue_style_violations(
                "音色需要你在产品的语音设置里改一下。",
                "声音可以成熟一点吗？",
            ),
        )

    async def test_generate_chat_reply_retries_unrequested_advice(self):
        repository = FakeConversationRepository()
        llm = SequenceLLM(["累了就歇会儿，别硬撑。", "听起来今天挺消耗人的。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=llm,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )

        result = await use_case.execute(user_id="user_a", message="今天有点累。")

        self.assertEqual("听起来今天挺消耗人的。", result.reply)
        self.assertEqual(2, len(llm.calls))

    async def test_generate_chat_reply_uses_narrow_fallback_after_failed_rewrite(self):
        repository = FakeConversationRepository()
        llm = SequenceLLM(["累了就歇会儿。", "今天别硬撑，好好休息吧。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            llm=llm,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )

        result = await use_case.execute(user_id="user_a", message="今天有点累。")

        self.assertEqual("那今天就聊点不费脑子的。", result.reply)
        self.assertEqual(2, len(llm.calls))

    def test_dialogue_fallback_keeps_advice_and_voice_boundaries(self):
        self.assertEqual(
            "好，不分析。你想说什么就说什么。",
            apply_dialogue_fallback(
                "先缓缓再说。",
                "我现在不想听建议。",
                ("unrequested_advice",),
            ),
        )
        self.assertEqual(
            "我明白，确实听着偏稚气。这个得改语音合成配置，光靠聊天内容改不了。",
            apply_dialogue_fallback(
                "去设置里换一下。",
                "声音能成熟一点吗？",
                ("unverified_settings",),
            ),
        )

    async def test_call_mode_returns_voice_and_persists_voice_message_types(self):
        voice_synthesizer = FakeVoiceReplySynthesizer()
        use_case, repository = self.build_send_use_case(voice_synthesizer=voice_synthesizer)

        result = await use_case.execute(
            user_id="user_a",
            message="hello",
            conversation_mode="call",
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertEqual(result.audio_urls, ("http://example.test/voice.mp3",))
        self.assertEqual(voice_synthesizer.received_replies, ["hello from echo"])
        self.assertEqual(repository.persisted_turns[0]["user_message_type"], "voice_asr")
        self.assertEqual(repository.persisted_turns[0]["assistant_message_type"], "voice_reply")

    async def test_call_mode_keeps_text_reply_when_voice_synthesis_fails(self):
        use_case, _ = self.build_send_use_case(voice_synthesizer=FailingVoiceReplySynthesizer())

        result = await use_case.execute(
            user_id="user_a",
            message="hello",
            conversation_mode="call",
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertEqual(result.audio_urls, ())

    async def test_chat_mode_does_not_synthesize_voice(self):
        voice_synthesizer = FakeVoiceReplySynthesizer()
        use_case, repository = self.build_send_use_case(voice_synthesizer=voice_synthesizer)

        result = await use_case.execute(user_id="user_a", message="hello")

        self.assertEqual(result.audio_urls, ())
        self.assertEqual(voice_synthesizer.received_replies, [])
        self.assertEqual(repository.persisted_turns[0]["user_message_type"], "text")
        self.assertEqual(repository.persisted_turns[0]["assistant_message_type"], "text")

    async def test_send_chat_message_passes_call_mode_to_context_provider(self):
        context_provider = FakeContextProvider()
        generator = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=context_provider,
            llm=FakeLLM(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
        )
        use_case = SendChatMessage(
            chat_reply_generator=generator,
            voice_reply_synthesizer=FakeVoiceReplySynthesizer(),
            request_guard=FakeChatRequestGuard(),
        )

        await use_case.execute(user_id="user_a", message="hello", conversation_mode="call")

        self.assertEqual(context_provider.conversation_modes, ["call"])

    async def test_send_chat_message_rejects_unknown_mode(self):
        use_case, _ = self.build_send_use_case()

        with self.assertRaises(ValueError):
            await use_case.execute(
                user_id="user_a",
                message="hello",
                conversation_mode="stream",
            )

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
