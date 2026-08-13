import unittest
from datetime import UTC, datetime

from features.agent.domain.delivery import (
    AgentDeliveryPlanError,
    build_natural_delivery_plan,
    parse_agent_delivery_plan,
    validate_agent_delivery_segments,
)
from features.agent.domain.entities import ContentPart
from features.chat.application.accept_message import AcceptChatMessage, ChatIntakePolicy
from features.chat.application.process_turns import ProcessPendingChatTurns
from features.chat.domain.delivery_timing import DeliveryTimingPolicy
from features.chat.domain.entities import (
    ChatAcceptedTurn,
    ChatBatchInput,
    ChatHistoryMessage,
    ChatMessageAcceptance,
    ChatQueueFullError,
    ChatReplyGroup,
    ChatTurnJob,
    ChatTurnStatus,
    ChatValidationError,
    PreparedChatReply,
)


def _message(message_id: int, role: str, content: str) -> ChatHistoryMessage:
    return ChatHistoryMessage(
        message_id=message_id,
        stable_message_id=f"msg-{message_id}",
        role=role,
        message_type="text",
        content=content,
        content_parts=(),
        created_at=datetime(2026, 8, 6, 8, message_id, tzinfo=UTC),
    )


def _intake_policy() -> ChatIntakePolicy:
    return ChatIntakePolicy(
        message_max_chars=10000,
        quiet_window_ms=2500,
        maximum_window_ms=10000,
        maximum_batch_messages=20,
        maximum_batch_characters=6000,
        maximum_queued_messages=20,
    )


def _timing_policy() -> DeliveryTimingPolicy:
    return DeliveryTimingPolicy(
        followup_text_delay_ms=1200,
        final_text_delay_ms=2000,
        sticker_delay_ms=1000,
    )


class FakeIntakeRepository:
    def __init__(self):
        self.calls = []
        self.error = None

    def accept_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return ChatMessageAcceptance(
            conversation_id="conv-1",
            message=_message(1, "user", str(kwargs["content"])),
            turn=ChatAcceptedTurn("turn-1", ChatTurnStatus.COLLECTING),
        )


class AcceptChatMessageTests(unittest.TestCase):
    def test_accepts_text_and_passes_queue_limits(self):
        repository = FakeIntakeRepository()

        result = AcceptChatMessage(repository, _intake_policy()).execute(
            user_id=" user-1 ",
            client_message_id="00000000-0000-4000-8000-000000000001",
            message_type="text",
            text=" hello ",
        )

        self.assertEqual(result.message.content, "hello")
        call = repository.calls[0]
        self.assertEqual(call["user_id"], "user-1")
        self.assertGreater(call["maximum_queued_messages"], 0)

    def test_validates_sticker_shape_and_client_id(self):
        use_case = AcceptChatMessage(FakeIntakeRepository(), _intake_policy())
        with self.assertRaises(ChatValidationError):
            use_case.execute(
                user_id="user-1",
                client_message_id="not-a-uuid",
                message_type="text",
                text="hello",
            )
        with self.assertRaises(ChatValidationError):
            use_case.execute(
                user_id="user-1",
                client_message_id="00000000-0000-4000-8000-000000000002",
                message_type="sticker",
            )

        result = use_case.execute(
            user_id="user-1",
            client_message_id="00000000-0000-4000-8000-000000000003",
            message_type="sticker",
            content_parts=(
                ContentPart(type="sticker", sticker_id="stk-wave", url="https://test/stk"),
            ),
        )
        self.assertEqual(result.conversation_id, "conv-1")

    def test_preserves_queue_full_error(self):
        repository = FakeIntakeRepository()
        repository.error = ChatQueueFullError("full")
        with self.assertRaises(ChatQueueFullError):
            AcceptChatMessage(repository, _intake_policy()).execute(
                user_id="user-1",
                client_message_id="00000000-0000-4000-8000-000000000004",
                message_type="text",
                text="hello",
            )


class AgentDeliveryPlanTests(unittest.TestCase):
    def test_builds_natural_segments_from_blank_lines(self):
        plan = build_natural_delivery_plan(
            "先休息一下。\n\n等状态回来再继续。",
            "chat",
        )

        self.assertEqual(plan.text_segments, ("先休息一下。", "等状态回来再继续。"))
        self.assertEqual(plan.sticker_placement, "after_text")

    def test_preserves_more_than_three_natural_paragraphs(self):
        paragraphs = tuple(f"第{index}个独立想法。" for index in range(1, 5))
        plan = build_natural_delivery_plan("\n\n".join(paragraphs), "chat")

        self.assertEqual(plan.text_segments, paragraphs)

    def test_merges_only_paragraphs_beyond_the_six_message_safety_limit(self):
        paragraphs = tuple(f"第{index}个独立想法。" for index in range(1, 9))
        plan = build_natural_delivery_plan("\n\n".join(paragraphs), "chat")

        self.assertEqual(len(plan.text_segments), 6)
        self.assertEqual(plan.text_segments[:5], paragraphs[:5])
        self.assertEqual(plan.text_segments[5], "\n\n".join(paragraphs[5:]))

    def test_splits_long_natural_reply_at_sentence_boundaries(self):
        sentences = tuple(f"这是第{index}句完整的话。" for index in range(1, 41))
        raw = "".join(sentences)
        plan = build_natural_delivery_plan(raw, "chat")

        self.assertGreater(len(plan.text_segments), 1)
        self.assertLessEqual(len(plan.text_segments), 6)
        self.assertTrue(all(segment.endswith("。") for segment in plan.text_segments))
        self.assertEqual("".join(plan.text_segments), raw)

    def test_natural_delivery_rejects_internal_markers_and_protocol_fragments(self):
        invalid_outputs = (
            "[消息时间 2026-08-13T09:00:00+08:00] 早上好。",
            "（本条消息为系统生成，无实际文本内容）",
            '回复是 {"text_segments":["你好"]}',
        )

        for raw in invalid_outputs:
            with self.subTest(raw=raw), self.assertRaises(AgentDeliveryPlanError):
                build_natural_delivery_plan(raw, "chat")

    def test_natural_delivery_allows_sticker_only_after_success(self):
        plan = build_natural_delivery_plan(
            "",
            "chat",
            sticker_placement="before_text",
            allow_empty=True,
        )

        self.assertEqual(plan.text_segments, ())
        self.assertEqual(plan.sticker_placement, "before_text")

    def test_legacy_delivery_cannot_override_tool_sticker_placement(self):
        plan = build_natural_delivery_plan(
            '{"text_segments":["给你。"],"sticker_placement":"before_text"}',
            "chat",
            sticker_placement="after_text",
        )

        self.assertEqual(plan.text_segments, ("给你。",))
        self.assertEqual(plan.sticker_placement, "after_text")

    def test_parses_exact_structured_delivery_contract(self):
        plan = parse_agent_delivery_plan(
            '{"text_segments":["one","two","three"],"sticker_placement":"before_text"}',
            "chat",
        )
        self.assertEqual(plan.text_segments, ("one", "two", "three"))
        self.assertEqual(plan.sticker_placement, "before_text")

    def test_rejects_plain_text_and_markdown_fences(self):
        invalid_outputs = (
            "ordinary reply",
            '```json\n{"text_segments":["one"],"sticker_placement":"after_text"}\n```',
        )

        for raw in invalid_outputs:
            with self.subTest(raw=raw), self.assertRaises(AgentDeliveryPlanError):
                parse_agent_delivery_plan(raw, "chat")

    def test_call_mode_keeps_one_plain_reply(self):
        raw = '{"text_segments":["one","two"]}'
        self.assertEqual(parse_agent_delivery_plan(raw, "call").text_segments, (raw,))

    def test_rejects_incomplete_structured_output_instead_of_returning_protocol_fragment(self):
        with self.assertRaises(AgentDeliveryPlanError) as context:
            parse_agent_delivery_plan('{"text_segments', "chat")
        self.assertEqual(context.exception.error_code, "llm_output_malformed")

    def test_rejects_incomplete_fenced_structured_output(self):
        with self.assertRaises(AgentDeliveryPlanError):
            parse_agent_delivery_plan('```json\n{"text_segments":["one"]\n```', "chat")

    def test_rejects_invalid_schema_shapes(self):
        invalid_outputs = (
            '{}',
            '{"text_segments":["one"]}',
            '{"text_segments":["one"],"sticker_placement":"after_text","extra":true}',
            '{"text_segments":"one","sticker_placement":"after_text"}',
            '{"text_segments":["one",2],"sticker_placement":"after_text"}',
            '{"text_segments":[""],"sticker_placement":"after_text"}',
            '{"text_segments":["one","one"],"sticker_placement":"after_text"}',
            '{"text_segments":["one","two","three","four"],"sticker_placement":"after_text"}',
            '{"text_segments":["one"],"sticker_placement":"middle"}',
            '{"text_segments":["one"],"text_segments":["two"],"sticker_placement":"after_text"}',
        )

        for raw in invalid_outputs:
            with self.subTest(raw=raw), self.assertRaises(AgentDeliveryPlanError):
                parse_agent_delivery_plan(raw, "chat")

    def test_rejects_json_with_surrounding_text_or_nested_protocol(self):
        invalid_outputs = (
            'hello {"text_segments":["hello"],"sticker_placement":"after_text"}',
            '{"text_segments":["hello"],"sticker_placement":"after_text"} trailing',
            '{"text_segments":["hello {\\"text_segments\\":[\\"hello\\"]}"],'
            '"sticker_placement":"after_text"}',
        )

        for raw in invalid_outputs:
            with self.subTest(raw=raw), self.assertRaises(AgentDeliveryPlanError):
                parse_agent_delivery_plan(raw, "chat")

    def test_rejects_internal_context_markers_in_segments(self):
        for marker in ("消息时间", "会话时间边界"):
            raw = (
                '{"text_segments":["['
                + marker
                + ' 2026-08-12T11:58:44+08:00]\\nhello"],'
                '"sticker_placement":"after_text"}'
            )
            with self.subTest(marker=marker), self.assertRaises(AgentDeliveryPlanError):
                parse_agent_delivery_plan(raw, "chat")

    def test_persistence_gate_rejects_protocol_fragments(self):
        with self.assertRaises(AgentDeliveryPlanError):
            validate_agent_delivery_segments(
                ('hello {"text_segments":["hello"]}',),
            )

    def test_rejects_internal_proactive_control_text(self):
        invalid_segments = (
            "（本条消息为系统生成，无实际文本内容）",
            "This is a system-generated proactive trigger, not an incoming user message.",
        )

        for segment in invalid_segments:
            with self.subTest(segment=segment), self.assertRaises(AgentDeliveryPlanError):
                validate_agent_delivery_segments((segment,))

    def test_proactive_mode_accepts_explicit_empty_delivery(self):
        plan = parse_agent_delivery_plan(
            '{"text_segments":[],"sticker_placement":"after_text"}',
            "proactive",
        )

        self.assertEqual(plan.text_segments, ())


class DeliveryTimingPolicyTests(unittest.TestCase):
    def test_delivery_uses_fixed_text_and_sticker_delays(self):
        policy = _timing_policy()
        presentation = policy.build(
            delivery_types=("text", "text", "sticker", "text"),
            agent_elapsed_ms=10_000,
        )

        self.assertEqual(presentation.initial_delay_ms, 0)
        self.assertEqual(presentation.message_delays_ms, (0, 1200, 1000, 2000))
        self.assertEqual(presentation.agent_elapsed_ms, 10_000)

    def test_sticker_first_still_waits_before_reveal(self):
        presentation = _timing_policy().build(
            delivery_types=("sticker", "text"),
            agent_elapsed_ms=0,
        )

        self.assertEqual(presentation.message_delays_ms, (1000, 1200))


class FakeTurnRepository:
    def __init__(self, turn, batch):
        self.turn = turn
        self.batch = batch
        self.rescheduled = []
        self.failed = []
        self.completed = []
        self.return_group = True

    def claim_due_turn(self, _lease_seconds):
        turn, self.turn = self.turn, None
        return turn

    def load_batch(self, _turn):
        return self.batch

    def complete_turn(self, turn, reply, presentation):
        self.completed.append((turn, reply, presentation))
        if not self.return_group:
            return None
        messages = tuple(
            _message(index + 10, "assistant", segment)
            for index, segment in enumerate(reply.reply_segments)
        )
        return ChatReplyGroup(
            turn_id=turn.turn_id,
            reply_group_id="reply-1",
            conversation_id=turn.conversation_id,
            messages=messages,
            presentation=presentation,
        )

    def fail_turn(self, turn_id, error_code):
        self.failed.append((turn_id, error_code))
        return True

    def reschedule_turn(self, turn_id, delay_ms):
        self.rescheduled.append((turn_id, delay_ms))
        return True


class FakeReplyGenerator:
    def __init__(self, prepared=None, error=None):
        self.prepared = prepared
        self.error = error
        self.finalized = []

    async def prepare(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.prepared

    async def finalize_persisted_turn(self, **kwargs):
        self.finalized.append(kwargs)


class FakeGuard:
    def __init__(self, available=True):
        self.available = available
        self.released = []

    def try_acquire(self, _user_id):
        return self.available

    def release(self, user_id):
        self.released.append(user_id)


class FakeEventBroker:
    def __init__(self):
        self.events = []

    async def publish(self, user_id, event):
        self.events.append((user_id, event))


def _turn_fixture() -> ChatTurnJob:
    return ChatTurnJob(
        turn_id="turn-1",
        user_id="user-1",
        conversation_id="conv-1",
        status=ChatTurnStatus.RUNNING,
        input_first_message_id=1,
        input_last_message_id=2,
        message_count=2,
        character_count=10,
        attempt_count=1,
        max_attempts=2,
    )


class ProcessPendingChatTurnsTests(unittest.IsolatedAsyncioTestCase):
    def _build(self, *, guard_available=True, generator_error=None):
        turn = _turn_fixture()
        batch = ChatBatchInput(
            turn=turn,
            messages=(_message(1, "user", "hello"),),
            combined_content="hello",
        )
        repository = FakeTurnRepository(turn, batch)
        generator = FakeReplyGenerator(
            prepared=PreparedChatReply(
                reply="one\ntwo",
                reply_segments=("one", "two"),
            ),
            error=generator_error,
        )
        guard = FakeGuard(guard_available)
        broker = FakeEventBroker()
        worker = ProcessPendingChatTurns(
            repository=repository,
            reply_generator=generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=_timing_policy(),
            lease_seconds=180,
        )
        return worker, repository, generator, guard, broker

    async def test_completes_one_turn_and_publishes_one_delivery_group(self):
        worker, repository, generator, guard, broker = self._build()

        self.assertTrue(await worker.run_once())

        self.assertEqual(len(repository.completed), 1)
        self.assertEqual(len(generator.finalized), 1)
        self.assertEqual(guard.released, ["user-1"])
        self.assertEqual(
            [event.event for _, event in broker.events],
            ["chat.typing.started", "chat.delivery.created", "chat.typing.stopped"],
        )
        delivery = broker.events[1][1]
        self.assertEqual(len(delivery.data["messages"]), 2)

    async def test_busy_guard_reschedules_without_starting_agent(self):
        worker, repository, generator, guard, broker = self._build(guard_available=False)

        self.assertTrue(await worker.run_once())

        self.assertEqual(repository.rescheduled, [("turn-1", 250)])
        self.assertEqual(repository.completed, [])
        self.assertEqual(generator.finalized, [])
        self.assertEqual(guard.released, [])
        self.assertEqual(broker.events, [])

    async def test_failure_is_recorded_and_does_not_publish_delivery(self):
        worker, repository, _, guard, broker = self._build(
            generator_error=RuntimeError("model failed")
        )

        self.assertTrue(await worker.run_once())

        self.assertEqual(repository.failed, [("turn-1", "RuntimeError")])
        self.assertEqual(guard.released, ["user-1"])
        self.assertEqual(
            [event.event for _, event in broker.events],
            ["chat.typing.started", "chat.turn.failed", "chat.typing.stopped"],
        )


if __name__ == "__main__":
    unittest.main()
