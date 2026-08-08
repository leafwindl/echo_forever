import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.application.execute_tool import ToolExecutor
from features.agent.domain.entities import AgentToolCall, AgentToolStatus
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.infrastructure.tools.schedule_tools import register_schedule_tools


class FakeScheduleRepository:
    def __init__(self, *, enabled=True, allow_echo_scheduling=True):
        self.preference = SimpleNamespace(
            enabled=enabled,
            allow_echo_scheduling=allow_echo_scheduling,
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


if __name__ == "__main__":
    unittest.main()
