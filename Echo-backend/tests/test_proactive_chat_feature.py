import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.application.execute_tool import ToolExecutor
from features.agent.domain.entities import AgentToolCall, AgentToolStatus
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.infrastructure.tools.schedule_tools import register_schedule_tools
from features.chat.domain.entities import PreparedChatReply
from features.proactive_chat.application.worker import ProcessProactiveChatJobs
from features.proactive_chat.domain.entities import ProactiveChatJob


class FakeScheduleRepository:
    def __init__(self, *, enabled=True, allow_echo_scheduling=True):
        self.preference = SimpleNamespace(
            enabled=enabled,
            allow_echo_scheduling=allow_echo_scheduling,
            pause_indefinite=False,
            paused_until=None,
        )
        self.created = []

    def get_preferences(self, _user_id):
        return self.preference

    def create_schedule(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(
            schedule_id="schedule_test",
            created_by=kwargs["created_by"],
            next_run_at=kwargs["local_datetime"].astimezone(UTC),
            timezone=kwargs["timezone"],
            user_visible_label=kwargs["user_visible_label"],
        )

    def list_schedules(self, _user_id):
        return ()

    def delete_schedule(self, _user_id, _schedule_id):
        return True


class ProactiveScheduleToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_reminder_is_created_as_user_request(self):
        repository = FakeScheduleRepository(enabled=False)
        registry = ToolRegistry()
        register_schedule_tools(registry, repository)

        result = await ToolExecutor(registry).execute(
            ToolExecutionContext(
                user_id="user_a",
                conversation_id="conv_a",
                trigger_message="明天晚上八点提醒我喝水",
            ),
            AgentToolCall(
                call_id="schedule",
                tool_name="create_chat_schedule",
                arguments={
                    "intent": "提醒用户喝水",
                    "schedule_type": "once",
                    "local_datetime": "2026-08-09T20:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                    "user_visible_label": "喝水提醒",
                },
            ),
        )

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(repository.created[0]["created_by"], "user_request")
        self.assertEqual(repository.created[0]["conversation_id"], "conv_a")

    async def test_echo_follow_up_requires_user_permission(self):
        repository = FakeScheduleRepository(enabled=True, allow_echo_scheduling=False)
        registry = ToolRegistry()
        register_schedule_tools(registry, repository)

        result = await ToolExecutor(registry).execute(
            ToolExecutionContext(
                user_id="user_a",
                trigger_message="我下午要去面试",
            ),
            AgentToolCall(
                call_id="schedule",
                tool_name="create_chat_schedule",
                arguments={
                    "intent": "面试后问候一次",
                    "schedule_type": "once",
                    "local_datetime": "2026-08-08T20:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                },
            ),
        )

        self.assertEqual(result.status, AgentToolStatus.FAILED)
        self.assertEqual(result.error_code, "echo_scheduling_disabled")
        self.assertEqual(repository.created, [])

    async def test_echo_follow_up_cannot_create_recurring_schedule(self):
        repository = FakeScheduleRepository()
        registry = ToolRegistry()
        register_schedule_tools(registry, repository)

        result = await ToolExecutor(registry).execute(
            ToolExecutionContext(user_id="user_a", trigger_message="我下午要去面试"),
            AgentToolCall(
                call_id="schedule",
                tool_name="create_chat_schedule",
                arguments={
                    "intent": "面试后问候",
                    "schedule_type": "daily",
                    "local_datetime": datetime(2026, 8, 9, 20, tzinfo=UTC).isoformat(),
                    "timezone": "Asia/Shanghai",
                },
            ),
        )

        self.assertEqual(result.status, AgentToolStatus.FAILED)
        self.assertEqual(result.error_code, "echo_can_only_create_once")


class _DeletedScheduleRepository:
    def __init__(self):
        self.job = ProactiveChatJob(
            job_id="job_deleted",
            schedule_id="schedule_deleted",
            user_id="user_a",
            conversation_id="conversation_a",
            scheduled_for=datetime(2026, 8, 8, 12, tzinfo=UTC),
            status="running",
            attempt_count=1,
            max_attempts=2,
        )
        self.suppressed = []

    def claim_due_job(self, _lease_seconds):
        return self.job

    def load_job_context(self, _job):
        return SimpleNamespace(enabled=True), None, "conversation_a"

    def suppress_job(self, job_id, reason):
        self.suppressed.append((job_id, reason))


class _DueSpontaneousJobRepository:
    def __init__(self, *, context_changes=()):
        self.job = ProactiveChatJob(
            job_id="job_due",
            schedule_id=None,
            user_id="user_a",
            conversation_id="conversation_a",
            scheduled_for=datetime(2026, 8, 10, 12, tzinfo=UTC),
            status="running",
            attempt_count=1,
            max_attempts=2,
        )
        self.preference = SimpleNamespace(
            enabled=True,
            allow_spontaneous_chat=True,
            allow_echo_scheduling=True,
            consecutive_unanswered=0,
            pause_indefinite=False,
            paused_until=None,
        )
        self.suppressed = []
        self.context_changes = list(context_changes)
        self.duplicate_delivery = False

    def claim_due_job(self, _lease_seconds):
        return self.job

    def load_job_context(self, _job):
        return self.preference, None, "conversation_a"

    def is_quiet(self, _preference, _now):
        return False

    def spontaneous_job_context_changed(self, _job):
        return self.context_changes.pop(0) if self.context_changes else False

    def has_recent_assistant_content(self, _user_id, _conversation_id, _segments):
        return self.duplicate_delivery

    def suppress_job(self, job_id, reason):
        self.suppressed.append((job_id, reason))


class _DueExplicitScheduleRepository(_DueSpontaneousJobRepository):
    def __init__(self):
        super().__init__()
        self.job = ProactiveChatJob(
            job_id="job_explicit",
            schedule_id="schedule_explicit",
            user_id="user_a",
            conversation_id="conversation_a",
            scheduled_for=datetime(2026, 8, 10, 12, tzinfo=UTC),
            status="running",
            attempt_count=1,
            max_attempts=2,
        )
        self.schedule = SimpleNamespace(
            schedule_id="schedule_explicit",
            created_by="user_request",
            intent="提醒用户喝水",
            status="active",
        )

    def load_job_context(self, _job):
        return self.preference, self.schedule, "conversation_a"


class ProactiveWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_schedule_job_is_suppressed_without_generating_reply(self):
        repository = _DeletedScheduleRepository()
        reply_generator = SimpleNamespace(prepare=AsyncMock())
        guard = SimpleNamespace(
            try_acquire=lambda _user_id: True,
            release=lambda _user_id: None,
        )
        broker = SimpleNamespace(publish=AsyncMock())
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(repository.suppressed, [("job_deleted", "schedule_deleted")])
        reply_generator.prepare.assert_not_awaited()
        broker.publish.assert_not_awaited()

    async def test_failed_agent_result_is_suppressed_without_delivery(self):
        repository = _DueSpontaneousJobRepository()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(
                return_value=PreparedChatReply(
                    reply="",
                    reply_segments=(),
                    error_code="llm_output_truncated",
                )
            )
        )
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        broker = SimpleNamespace(publish=AsyncMock())
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(
            repository.suppressed,
            [("job_due", "agent_failed:llm_output_truncated")],
        )
        broker.publish.assert_not_awaited()

    async def test_failed_planner_result_keeps_specific_error_code_without_delivery(self):
        repository = _DueSpontaneousJobRepository()
        repository.persist_delivery = Mock()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(
                return_value=PreparedChatReply(
                    reply="",
                    reply_segments=(),
                    error_code="planner_output_invalid",
                )
            )
        )
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=SimpleNamespace(
                try_acquire=lambda _user_id: True,
                release=lambda _user_id: None,
            ),
            event_broker=SimpleNamespace(publish=AsyncMock()),
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(repository.suppressed, [("job_due", "planner_output_invalid")])
        repository.persist_delivery.assert_not_called()

    async def test_internal_control_output_is_suppressed_before_persistence(self):
        repository = _DueSpontaneousJobRepository()
        repository.persist_delivery = Mock()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(
                return_value=PreparedChatReply(
                    reply="（本条消息为系统生成，无实际文本内容）",
                    reply_segments=("（本条消息为系统生成，无实际文本内容）",),
                )
            )
        )
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        broker = SimpleNamespace(publish=AsyncMock())
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(repository.suppressed, [("job_due", "agent_output_rejected")])
        repository.persist_delivery.assert_not_called()
        broker.publish.assert_not_awaited()

    async def test_changed_spontaneous_context_is_suppressed_before_generation(self):
        repository = _DueSpontaneousJobRepository(context_changes=(True,))
        reply_generator = SimpleNamespace(prepare=AsyncMock())
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        broker = SimpleNamespace(publish=AsyncMock())
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(
            repository.suppressed,
            [("job_due", "spontaneous_context_changed")],
        )
        reply_generator.prepare.assert_not_awaited()
        broker.publish.assert_not_awaited()

    async def test_context_change_during_generation_is_suppressed_before_persistence(self):
        repository = _DueSpontaneousJobRepository(context_changes=(False, True))
        repository.persist_delivery = Mock()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(
                return_value=PreparedChatReply(
                    reply="Good morning",
                    reply_segments=("Good morning",),
                )
            )
        )
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        broker = SimpleNamespace(publish=AsyncMock())
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=broker,
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(
            repository.suppressed,
            [("job_due", "spontaneous_context_changed")],
        )
        repository.persist_delivery.assert_not_called()
        broker.publish.assert_not_awaited()

    async def test_proactive_prompt_forbids_assuming_current_user_activity(self):
        repository = _DueSpontaneousJobRepository()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(return_value=PreparedChatReply(reply="", reply_segments=()))
        )
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=SimpleNamespace(publish=AsyncMock()),
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        await worker.run_once()

        prompt = reply_generator.prepare.await_args.kwargs["message"]
        self.assertIn("not an incoming user message", prompt)
        self.assertIn("awake, online, reading", prompt)
        self.assertIn("return no user-visible text", prompt)
        self.assertNotIn("text_segments", prompt)
        prepare_kwargs = reply_generator.prepare.await_args.kwargs
        self.assertEqual("", prepare_kwargs["proactive_intent"])
        self.assertFalse(prepare_kwargs["proactive_force_send"])

    async def test_explicit_schedule_forces_send_plan_with_approved_intent(self):
        repository = _DueExplicitScheduleRepository()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(return_value=PreparedChatReply(reply="", reply_segments=()))
        )
        guard = SimpleNamespace(try_acquire=lambda _user_id: True, release=lambda _user_id: None)
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=guard,
            event_broker=SimpleNamespace(publish=AsyncMock()),
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        await worker.run_once()

        prepare_kwargs = reply_generator.prepare.await_args.kwargs
        self.assertEqual("提醒用户喝水", prepare_kwargs["proactive_intent"])
        self.assertTrue(prepare_kwargs["proactive_force_send"])

    async def test_duplicate_spontaneous_delivery_is_suppressed_before_persistence(self):
        repository = _DueSpontaneousJobRepository()
        repository.duplicate_delivery = True
        repository.persist_delivery = Mock()
        reply_generator = SimpleNamespace(
            prepare=AsyncMock(
                return_value=PreparedChatReply(
                    reply="晚上好，有空聊聊吗？",
                    reply_segments=("晚上好，有空聊聊吗？",),
                )
            )
        )
        worker = ProcessProactiveChatJobs(
            repository=repository,
            reply_generator=reply_generator,
            request_guard=SimpleNamespace(
                try_acquire=lambda _user_id: True,
                release=lambda _user_id: None,
            ),
            event_broker=SimpleNamespace(publish=AsyncMock()),
            timing_policy=SimpleNamespace(),
            lease_seconds=30,
        )

        processed = await worker.run_once()

        self.assertTrue(processed)
        self.assertEqual(repository.suppressed, [("job_due", "duplicate_delivery")])
        repository.persist_delivery.assert_not_called()


if __name__ == "__main__":
    unittest.main()
