import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import (
    AgentTurnResult,
    ContentPart,
    ProactiveAction,
    ProactiveDecision,
)
from features.agent.domain.services import ProactivePlannerError
from features.chat.application.clear_context import ClearChatContext
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.send_message import SendChatMessage
from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.domain.entities import (
    ChatContext,
    ChatRequestClaim,
    ChatRequestClaimStatus,
    ChatRequestInProgressError,
    ChatValidationError,
    MemoryExtractionScheduleResult,
)
from features.chat.infrastructure.context_builder import should_prioritize_proactive_sticker


class FakeConversationRepository:
    def __init__(self):
        self.persisted_turns = []
        self.cleared_user_ids = []
        self.user_message_count = 1

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
        user_content_parts=(),
        assistant_content_parts=(),
    ):
        self.persisted_turns.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "user_message": user_message,
                "assistant_reply": assistant_reply,
                "user_message_type": user_message_type,
                "assistant_message_type": assistant_message_type,
                "user_content_parts": user_content_parts,
                "assistant_content_parts": assistant_content_parts,
            }
        )
        return 10, 11

    def clear_context(self, user_id):
        self.cleared_user_ids.append(user_id)
        return 4, 1

    def count_user_messages(self, user_id, conversation_id):
        return self.user_message_count

    def list_recent_user_messages(self, user_id, conversation_id, limit):
        del user_id, conversation_id
        messages = [
            (index + 1, turn["user_message"]) for index, turn in enumerate(self.persisted_turns)
        ]
        return tuple(messages[-limit:])


class FakeContextProvider:
    def __init__(self):
        self.conversation_modes = []

    async def build_context(self, user_id, user_message, conversation_id, conversation_mode):
        self.conversation_modes.append(conversation_mode)
        return ChatContext(
            messages=[{"role": "user", "content": user_message}],
            history_messages=[],
        )


class SequenceAgentOrchestrator:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def run(
        self,
        user_id,
        message,
        messages,
        conversation_mode="chat",
        sticker_intent="",
        allow_proactive_stickers=True,
        proactive_sticker_due=False,
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "messages": messages,
                "conversation_mode": conversation_mode,
                "sticker_intent": sticker_intent,
                "allow_proactive_stickers": allow_proactive_stickers,
                "proactive_sticker_due": proactive_sticker_due,
            }
        )
        reply = self.replies.pop(0) if self.replies else "hello from echo"
        return reply if isinstance(reply, AgentTurnResult) else AgentTurnResult(reply_text=reply)


class FakeProactivePlanner:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    async def decide(self, messages, available_fact_ids, *, force_send=False):
        self.calls.append(
            {
                "messages": list(messages),
                "available_fact_ids": tuple(available_fact_ids),
                "force_send": force_send,
            }
        )
        return self.decision


class FailedProactivePlanner:
    def __init__(self, code):
        self.code = code
        self.calls = []

    async def decide(self, messages, available_fact_ids, *, force_send=False):
        self.calls.append(
            {
                "messages": list(messages),
                "available_fact_ids": tuple(available_fact_ids),
                "force_send": force_send,
            }
        )
        raise ProactivePlannerError(self.code)


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
    def __init__(self):
        self.calls = []

    def schedule(
        self,
        user_id,
        user_message,
        assistant_reply,
        source_message_id,
        candidate_user_messages,
        force_batch_review,
    ):
        self.calls.append((candidate_user_messages, force_batch_review))
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


class FakeStickerAgentOrchestrator:
    async def run(
        self,
        user_id,
        message,
        messages,
        conversation_mode="chat",
        sticker_intent="",
        allow_proactive_stickers=True,
        proactive_sticker_due=False,
    ):
        return AgentTurnResult(
            reply_text="给你，这张很适合现在。",
            content_parts=(
                ContentPart(
                    type="sticker",
                    sticker_id="stk_wave",
                    url="https://example.test/wave.png",
                ),
            ),
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


class FakeChatRequestResultRepository:
    def __init__(self):
        self.records = {}
        self.complete_calls = []
        self.abandon_calls = []

    def claim(self, user_id, request_id, request_fingerprint):
        key = (user_id, request_id)
        record = self.records.get(key)
        if record is None:
            self.records[key] = {
                "fingerprint": request_fingerprint,
                "status": "processing",
                "result": None,
            }
            return ChatRequestClaim(status=ChatRequestClaimStatus.CLAIMED)
        if record["fingerprint"] != request_fingerprint:
            return ChatRequestClaim(status=ChatRequestClaimStatus.CONFLICT)
        if record["status"] == "completed":
            return ChatRequestClaim(
                status=ChatRequestClaimStatus.COMPLETED,
                result=record["result"],
            )
        return ChatRequestClaim(status=ChatRequestClaimStatus.IN_PROGRESS)

    def complete(self, user_id, request_id, request_fingerprint, result):
        key = (user_id, request_id)
        self.records[key] = {
            "fingerprint": request_fingerprint,
            "status": "completed",
            "result": result,
        }
        self.complete_calls.append(key)

    def abandon(self, user_id, request_id, request_fingerprint):
        key = (user_id, request_id)
        record = self.records.get(key)
        if record and record["fingerprint"] == request_fingerprint:
            self.records.pop(key)
        self.abandon_calls.append(key)


class ProactiveStickerCadenceTests(unittest.TestCase):
    def test_third_turn_enters_priority_window(self):
        self.assertFalse(
            should_prioritize_proactive_sticker(
                allow_proactive_stickers=True,
                completed_turns_without_sticker=1,
                target_turns=3,
            )
        )
        self.assertTrue(
            should_prioritize_proactive_sticker(
                allow_proactive_stickers=True,
                completed_turns_without_sticker=2,
                target_turns=3,
            )
        )

    def test_cooldown_blocks_priority_window(self):
        self.assertFalse(
            should_prioritize_proactive_sticker(
                allow_proactive_stickers=False,
                completed_turns_without_sticker=10,
                target_turns=3,
            )
        )


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
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            relationship_recorder=relationship_recorder,
            agent_orchestrator=SequenceAgentOrchestrator(["hello from echo"]),
        )
        return use_case, repository

    def build_send_use_case(
        self,
        voice_synthesizer=None,
        request_guard=None,
        request_result_repository=None,
    ):
        chat_reply_generator, repository = self.build_generate_use_case()
        use_case = SendChatMessage(
            chat_reply_generator=chat_reply_generator,
            voice_reply_synthesizer=voice_synthesizer or FakeVoiceReplySynthesizer(),
            request_guard=request_guard or FakeChatRequestGuard(),
            request_result_repository=request_result_repository,
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
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            relationship_recorder=recorder,
            agent_orchestrator=SequenceAgentOrchestrator(["hello from echo"]),
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
            summary_updater=summary_updater,
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=SequenceAgentOrchestrator(["hello from echo"]),
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

    async def test_generate_chat_reply_applies_style_fallback_without_second_reply_path(self):
        repository = FakeConversationRepository()
        candidate = "（轻轻抱住你）别难过。"
        agent = SequenceAgentOrchestrator([candidate])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(user_id="user_a", message="我今天很难过")

        violations = find_dialogue_style_violations(candidate, "我今天很难过")
        self.assertEqual(
            apply_dialogue_fallback(candidate, "我今天很难过", violations),
            result.reply,
        )
        self.assertEqual(1, len(agent.calls))
        self.assertEqual(result.reply, repository.persisted_turns[0]["assistant_reply"])

    async def test_generate_chat_reply_sanitizes_stage_direction(self):
        repository = FakeConversationRepository()
        candidate = "Echo：［轻轻点头］我会认真听。"
        agent = SequenceAgentOrchestrator([candidate])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(user_id="user_a", message="陪我说说话")

        self.assertEqual("我会认真听。", result.reply)
        self.assertEqual(1, len(agent.calls))

    async def test_proactive_reply_removes_fake_sticker_delivery_narration(self):
        candidate = "（附上一张安静的表情包，当作睡前的小回应。）\n\n叶子，好好睡，明天见。"
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=SequenceAgentOrchestrator([candidate]),
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="internal proactive trigger",
            conversation_id="conv_active",
            conversation_mode="proactive",
        )

        self.assertEqual("叶子，好好睡，明天见。", prepared.reply)
        self.assertEqual(("叶子，好好睡，明天见。",), prepared.reply_segments)

    async def test_style_fallback_rebuilds_segments_and_accepts_server_weekday(self):
        class LiveSessionContextProvider:
            async def build_context(
                self,
                user_id,
                user_message,
                conversation_id,
                conversation_mode,
            ):
                del user_id, conversation_id, conversation_mode
                return ChatContext(
                    messages=[{"role": "user", "content": user_message}],
                    history_messages=[],
                    suppress_repeated_greeting=True,
                    temporal_context={"weekday": "周六"},
                )

        candidate = AgentTurnResult(
            reply_text="中午好，叶子。今天周六。\n下午的汇报先听完整体思路。",
            reply_segments=(
                "中午好，叶子。今天周六。",
                "下午的汇报先听完整体思路。",
            ),
        )
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=LiveSessionContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=SequenceAgentOrchestrator([candidate]),
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="下午要听PPT汇报",
            conversation_id="conv_active",
        )

        self.assertEqual(
            ("叶子。今天周六。", "下午的汇报先听完整体思路。"),
            prepared.reply_segments,
        )
        self.assertEqual(
            "叶子。今天周六。\n下午的汇报先听完整体思路。",
            prepared.reply,
        )

    async def test_proactive_reply_suppresses_sticker_narration_only_output(self):
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=SequenceAgentOrchestrator(["（附上一张安静的表情包。）"]),
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="internal proactive trigger",
            conversation_id="conv_active",
            conversation_mode="proactive",
        )

        self.assertEqual("", prepared.reply)
        self.assertEqual((), prepared.reply_segments)

    async def test_proactive_planner_skip_never_calls_writer(self):
        agent = SequenceAgentOrchestrator(["不应生成"])
        planner = FakeProactivePlanner(
            ProactiveDecision(action=ProactiveAction.SKIP, reason="no_natural_topic")
        )
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
            proactive_planner=planner,
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="internal proactive trigger",
            conversation_id="conv_active",
            conversation_mode="proactive",
        )

        self.assertEqual("", prepared.reply)
        self.assertEqual((), prepared.reply_segments)
        self.assertEqual(1, len(planner.calls))
        self.assertEqual([], agent.calls)

    async def test_proactive_planner_failure_is_preserved_as_technical_error(self):
        agent = SequenceAgentOrchestrator(["不应生成"])
        planner = FailedProactivePlanner("planner_output_invalid")
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
            proactive_planner=planner,
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="internal proactive trigger",
            conversation_id="conv_active",
            conversation_mode="proactive",
        )

        self.assertEqual("", prepared.reply)
        self.assertEqual((), prepared.reply_segments)
        self.assertEqual("planner_output_invalid", prepared.error_code)
        self.assertEqual([], agent.calls)

    async def test_proactive_writer_receives_only_selected_safe_facts(self):
        class ProactiveContextProvider:
            async def build_context(
                self, user_id, user_message, conversation_id, conversation_mode
            ):
                del user_id, user_message, conversation_id, conversation_mode
                return ChatContext(
                    messages=[
                        {
                            "role": "user",
                            "content": "[消息时间 2026-08-14T17:33:20+08:00] 准备吃饭。",
                        }
                    ],
                    history_messages=[],
                    proactive_writer_messages=[
                        {"role": "system", "content": "Echo persona"}
                    ],
                    proactive_safe_facts={
                        "conversation_gap": "距上一条真实用户消息约 2小时50分钟。",
                        "last_user_message": "上一条用户消息：准备吃饭。",
                    },
                )

        planner = FakeProactivePlanner(
            ProactiveDecision(
                action=ProactiveAction.SEND,
                topic="casual_check_in",
                tone="gentle",
                safe_fact_ids=("conversation_gap",),
            )
        )
        agent = SequenceAgentOrchestrator(["晚上好，有空的时候来聊聊吧。"])
        use_case = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=ProactiveContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
            proactive_planner=planner,
        )

        prepared = await use_case.prepare(
            user_id="user_a",
            message="internal proactive trigger",
            conversation_id="conv_active",
            conversation_mode="proactive",
        )

        writer_content = "\n".join(
            str(item.get("content") or "") for item in agent.calls[0]["messages"]
        )
        planner_content = "\n".join(
            str(item.get("content") or "")
            for item in planner.calls[0]["messages"]
        )
        self.assertIn("[消息时间", planner_content)
        self.assertNotIn("[消息时间", writer_content)
        self.assertIn("2小时50分钟", writer_content)
        self.assertNotIn("准备吃饭", writer_content)
        self.assertEqual("晚上好，有空的时候来聊聊吧。", prepared.reply)

    async def test_generate_chat_reply_pauses_questions_after_two_question_turns(self):
        repository = FakeConversationRepository()
        context_provider = FakeContextProvider()

        async def build_context(user_id, user_message, conversation_id, conversation_mode):
            del user_id, conversation_id, conversation_mode
            return ChatContext(
                messages=[{"role": "user", "content": user_message}],
                history_messages=[],
                pause_followup_questions=True,
            )

        context_provider.build_context = build_context
        candidate = "这听起来挺有意思的。你还想说哪一部分？"
        agent = SequenceAgentOrchestrator([candidate])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=context_provider,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(user_id="user_a", message="我们平时会聊一点")

        violations = find_dialogue_style_violations(
            candidate,
            "我们平时会聊一点",
            pause_followup_questions=True,
        )
        self.assertEqual(
            apply_dialogue_fallback(candidate, "我们平时会聊一点", violations),
            result.reply,
        )
        self.assertEqual(1, len(agent.calls))

    async def test_generate_chat_reply_preserves_one_grounded_exploration_question(self):
        repository = FakeConversationRepository()
        candidate = (
            "我觉得你舍不得的可能不只是项目，还有已经投入进去的期待。"
            "你现在更舍不得项目本身，还是已经花掉的时间？"
        )
        agent = SequenceAgentOrchestrator([candidate])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(
            user_id="user_a",
            message="最近做这个项目越来越没动力，但放弃又觉得可惜",
        )

        self.assertEqual(candidate, result.reply)
        self.assertNotIn(
            "multiple_questions",
            find_dialogue_style_violations(candidate, result.user_message),
        )

    async def test_every_fifth_user_turn_requests_batch_memory_review(self):
        repository = FakeConversationRepository()
        repository.user_message_count = 5
        scheduler = FakeMemoryScheduler()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=scheduler,
            agent_orchestrator=SequenceAgentOrchestrator(["hello from echo"]),
        )

        await use_case.execute(user_id="user_a", message="普通但可能有长期信息的一句话")

        self.assertTrue(scheduler.calls[0][1])
        self.assertEqual(scheduler.calls[0][0][-1][1], "普通但可能有长期信息的一句话")

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

    async def test_generate_chat_reply_applies_unrequested_advice_fallback(self):
        repository = FakeConversationRepository()
        agent = SequenceAgentOrchestrator(["累了就歇会儿，别硬撑。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(user_id="user_a", message="今天有点累。")

        self.assertEqual("那今天就聊点不费脑子的。", result.reply)
        self.assertEqual(1, len(agent.calls))

    async def test_generate_chat_reply_uses_narrow_fallback_for_single_agent_final(self):
        repository = FakeConversationRepository()
        agent = SequenceAgentOrchestrator(["累了就歇会儿。"])
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=agent,
        )

        result = await use_case.execute(user_id="user_a", message="今天有点累。")

        self.assertEqual("那今天就聊点不费脑子的。", result.reply)
        self.assertEqual(1, len(agent.calls))

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

    async def test_sticker_message_type_is_persisted_and_echo_replies(self):
        use_case, repository = self.build_send_use_case()
        user_sticker = ContentPart(
            type="sticker",
            sticker_id="stk_user",
            url="https://example.test/user.png",
        )

        result = await use_case.execute(
            user_id="user_a",
            message="用户发送了一张表情包。描述：开心挥手。语义标签：开心、挥手。",
            user_message_type="sticker",
            sticker_intent="开心 挥手",
            user_content_parts=(user_sticker,),
        )

        self.assertEqual(result.reply, "hello from echo")
        self.assertEqual(repository.persisted_turns[0]["user_message_type"], "sticker")
        self.assertEqual(
            repository.persisted_turns[0]["user_content_parts"],
            (user_sticker,),
        )

    async def test_unified_agent_result_persists_natural_text_and_sticker(self):
        repository = FakeConversationRepository()
        use_case = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=FakeStickerAgentOrchestrator(),
        )

        result = await use_case.execute(user_id="user_a", message="发个表情包")

        self.assertEqual(result.reply, "给你，这张很适合现在。")
        self.assertEqual(result.content_parts[0].sticker_id, "stk_wave")
        self.assertEqual(
            repository.persisted_turns[0]["assistant_reply"],
            "给你，这张很适合现在。",
        )
        self.assertEqual(
            repository.persisted_turns[0]["assistant_content_parts"][0].sticker_id,
            "stk_wave",
        )

    async def test_call_mode_drops_agent_sticker_before_persistence_and_delivery(self):
        repository = FakeConversationRepository()
        generator = GenerateChatReply(
            conversation_repository=repository,
            context_provider=FakeContextProvider(),
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=FakeStickerAgentOrchestrator(),
        )
        use_case = SendChatMessage(
            chat_reply_generator=generator,
            voice_reply_synthesizer=FakeVoiceReplySynthesizer(),
            request_guard=FakeChatRequestGuard(),
        )

        result = await use_case.execute(
            user_id="user_a",
            message="发一个表情包",
            conversation_mode="call",
        )

        self.assertEqual([part.type for part in result.content_parts], ["text"])
        self.assertEqual(repository.persisted_turns[0]["assistant_content_parts"], ())

    async def test_send_chat_message_passes_call_mode_to_context_provider(self):
        context_provider = FakeContextProvider()
        generator = GenerateChatReply(
            conversation_repository=FakeConversationRepository(),
            context_provider=context_provider,
            summary_updater=FakeSummaryUpdater(),
            memory_scheduler=FakeMemoryScheduler(),
            agent_orchestrator=SequenceAgentOrchestrator(["hello from echo"]),
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

    async def test_chat_request_id_replays_completed_result_without_duplicate_turn(self):
        request_results = FakeChatRequestResultRepository()
        use_case, repository = self.build_send_use_case(request_result_repository=request_results)

        first = await use_case.execute(
            user_id="user_a",
            message="hello",
            request_id="request_same",
        )
        second = await use_case.execute(
            user_id="user_a",
            message="hello",
            request_id="request_same",
        )

        self.assertEqual(first, second)
        self.assertEqual(len(repository.persisted_turns), 1)
        self.assertEqual(request_results.complete_calls, [("user_a", "request_same")])

    async def test_chat_request_id_rejects_different_content(self):
        request_results = FakeChatRequestResultRepository()
        use_case, repository = self.build_send_use_case(request_result_repository=request_results)
        await use_case.execute(
            user_id="user_a",
            message="first",
            request_id="request_conflict",
        )

        with self.assertRaisesRegex(ValueError, "request_id"):
            await use_case.execute(
                user_id="user_a",
                message="second",
                request_id="request_conflict",
            )

        self.assertEqual(len(repository.persisted_turns), 1)


if __name__ == "__main__":
    unittest.main()
