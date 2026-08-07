import unittest
from datetime import UTC, datetime

from features.agent.domain.delivery import parse_agent_delivery_plan
from features.agent.domain.entities import ContentPart
from features.chat.application.accept_message import AcceptChatMessage
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

        result = AcceptChatMessage(repository).execute(
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
        use_case = AcceptChatMessage(FakeIntakeRepository())
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
            AcceptChatMessage(repository).execute(
                user_id="user-1",
                client_message_id="00000000-0000-4000-8000-000000000004",
                message_type="text",
                text="hello",
            )


class AgentDeliveryPlanTests(unittest.TestCase):
    def test_parses_structured_delivery_and_limits_segments(self):
        plan = parse_agent_delivery_plan(
            '{"text_segments":["one","two","three","four"],'
            '"sticker_placement":"before_text"}',
            "chat",
        )
        self.assertEqual(plan.text_segments, ("one", "two", "three"))
        self.assertEqual(plan.sticker_placement, "before_text")

    def test_accepts_code_fence_and_falls_back_to_plain_text(self):
        fenced = parse_agent_delivery_plan(
            '```json\n{"text_segments":["one"]}\n```',
            "chat",
        )
        plain = parse_agent_delivery_plan("ordinary reply", "chat")
        invalid_placement = parse_agent_delivery_plan(
            '{"text_segments":["one"],"sticker_placement":"middle"}',
            "chat",
        )
        self.assertEqual(fenced.text_segments, ("one",))
        self.assertEqual(plain.text_segments, ("ordinary reply",))
        self.assertEqual(invalid_placement.sticker_placement, "after_text")

    def test_call_mode_keeps_one_plain_reply(self):
        raw = '{"text_segments":["one","two"]}'
        self.assertEqual(parse_agent_delivery_plan(raw, "call").text_segments, (raw,))


class DeliveryTimingPolicyTests(unittest.TestCase):
    def test_longer_text_waits_longer_and_agent_time_is_deducted(self):
        policy = DeliveryTimingPolicy()
        short = policy.build(
            text_segments=("short",),
            delivery_types=("text",),
            agent_elapsed_ms=0,
        )
        long = policy.build(
            text_segments=("x" * 100,),
            delivery_types=("text",),
            agent_elapsed_ms=0,
        )
        already_slow = policy.build(
            text_segments=("x" * 100,),
            delivery_types=("text",),
            agent_elapsed_ms=10_000,
        )

        self.assertGreater(sum(long.message_delays_ms), sum(short.message_delays_ms))
        self.assertEqual(already_slow.message_delays_ms, (0,))
        self.assertLessEqual(sum(long.message_delays_ms), 2500)


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
            timing_policy=DeliveryTimingPolicy(),
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
