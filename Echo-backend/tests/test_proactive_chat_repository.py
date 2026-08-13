import sys
import unittest
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.proactive_chat.domain.entities import (
    ChatSchedule,
    ProactiveChatJob,
    ProactiveChatPreferences,
)
from features.proactive_chat.infrastructure import postgres_repository as repository_module
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)


class _FakeCursor:
    def __init__(self, *, one=None, many=()):
        self.one = one
        self.many = many
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        value, self.one = self.one, None
        return value

    def fetchall(self):
        return self.many


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class ProactiveRepositoryTests(unittest.TestCase):
    @staticmethod
    def _preference(**overrides):
        values = {
            "user_id": "user_a",
            "enabled": True,
            "allow_echo_scheduling": True,
            "allow_spontaneous_chat": True,
            "proactivity_level": "active",
            "timezone": "Asia/Shanghai",
            "quiet_start": time(22, 30),
            "quiet_end": time(8),
            "explicit_reminder_quiet_policy": "defer",
            "notification_preview": False,
            "proactive_count": 0,
            "window_started_at": None,
            "last_proactive_at": None,
            "consecutive_unanswered": 0,
        }
        values.update(overrides)
        return ProactiveChatPreferences(**values)

    def test_spontaneous_candidate_query_excludes_unanswered_pause(self):
        cursor = _FakeCursor(many=[])
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            created = PostgresProactiveChatRepository().create_spontaneous_job_if_due()
        finally:
            repository_module.transaction = original_transaction

        self.assertFalse(created)
        self.assertIn("pref.consecutive_unanswered < 2", cursor.calls[0][0])

    def test_spontaneous_candidate_query_applies_recent_failure_cooldown(self):
        cursor = _FakeCursor(many=[])
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            PostgresProactiveChatRepository().create_spontaneous_job_if_due()
        finally:
            repository_module.transaction = original_transaction

        query = cursor.calls[0][0]
        self.assertIn("recent_failure.updated_at > NOW() - INTERVAL '10 minutes'", query)
        self.assertIn("recent_failure.error_code LIKE 'agent_failed:%'", query)

    def test_spontaneous_policy_pauses_after_two_unanswered_messages(self):
        now = datetime(2026, 8, 10, 8, tzinfo=UTC)
        allowed = PostgresProactiveChatRepository()._spontaneous_allowed(
            self._preference(consecutive_unanswered=2),
            now - timedelta(hours=3),
            now,
        )

        self.assertFalse(allowed)

    def test_active_six_message_limit_uses_rolling_24_hour_window(self):
        now = datetime(2026, 8, 10, 8, tzinfo=UTC)
        repository = PostgresProactiveChatRepository()
        blocked = repository._spontaneous_allowed(
            self._preference(
                proactive_count=6,
                window_started_at=now - timedelta(hours=23),
                last_proactive_at=now - timedelta(hours=3),
            ),
            now - timedelta(hours=3),
            now,
        )
        reset = repository._spontaneous_allowed(
            self._preference(
                proactive_count=6,
                window_started_at=now - timedelta(hours=24),
                last_proactive_at=now - timedelta(hours=3),
            ),
            now - timedelta(hours=3),
            now,
        )

        self.assertFalse(blocked)
        self.assertTrue(reset)

    def test_delete_schedule_removes_row_and_suppresses_pending_jobs(self):
        cursor = _FakeCursor(one={"schedule_id": "schedule_a"})
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            deleted = PostgresProactiveChatRepository().delete_schedule("user_a", "schedule_a")
        finally:
            repository_module.transaction = original_transaction

        self.assertTrue(deleted)
        queries = [call[0] for call in cursor.calls]
        self.assertIn("UPDATE proactive_chat_jobs", queries[1])
        self.assertIn("SET status = 'suppressed'", queries[1])
        self.assertIn("DELETE FROM chat_schedules", queries[2])

    def test_delete_schedule_returns_false_for_unknown_row(self):
        cursor = _FakeCursor(one=None)
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            deleted = PostgresProactiveChatRepository().delete_schedule("user_a", "missing")
        finally:
            repository_module.transaction = original_transaction

        self.assertFalse(deleted)
        self.assertEqual(len(cursor.calls), 1)

    def test_spontaneous_job_context_change_uses_messages_after_job_creation(self):
        cursor = _FakeCursor(one={"context_changed": True})
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        job = ProactiveChatJob(
            job_id="job_a",
            schedule_id=None,
            user_id="user_a",
            conversation_id="conversation_a",
            scheduled_for=datetime(2026, 8, 11, 0, tzinfo=UTC),
            status="running",
            attempt_count=2,
            max_attempts=2,
        )
        try:
            changed = PostgresProactiveChatRepository().spontaneous_job_context_changed(job)
        finally:
            repository_module.transaction = original_transaction

        self.assertTrue(changed)
        query, params = cursor.calls[0]
        self.assertIn("message.created_at > current_job.created_at", query)
        self.assertIn("message.role = 'user'", query)
        self.assertIn("message.status = 'active'", query)
        self.assertEqual(params, ("job_a", "user_a"))

    def test_once_schedule_is_deleted_after_successful_advance(self):
        cursor = _FakeCursor()
        schedule = ChatSchedule(
            schedule_id="schedule_once",
            user_id="user_a",
            conversation_id="conversation_a",
            created_by="user_request",
            schedule_type="once",
            intent="drink water",
            user_visible_label="Water",
            timezone="UTC",
            next_run_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
            recurrence_rule={},
            status="active",
            run_count=0,
            max_runs=1,
            last_run_at=None,
        )

        PostgresProactiveChatRepository()._advance_schedule(
            cursor, schedule, datetime(2026, 8, 8, 12, 1, tzinfo=UTC)
        )

        self.assertEqual(len(cursor.calls), 1)
        self.assertIn("DELETE FROM chat_schedules", cursor.calls[0][0])

    def test_list_schedules_purges_terminal_and_stale_once_rows(self):
        cursor = _FakeCursor(many=[])
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            schedules = PostgresProactiveChatRepository().list_schedules("user_a")
        finally:
            repository_module.transaction = original_transaction

        self.assertEqual(schedules, ())
        self.assertIn("DELETE FROM chat_schedules", cursor.calls[0][0])
        self.assertIn("status IN ('cancelled', 'completed')", cursor.calls[0][0])
        self.assertIn("INTERVAL '30 minutes'", cursor.calls[0][0])
        self.assertIn("INTERVAL '60 minutes'", cursor.calls[0][0])


if __name__ == "__main__":
    unittest.main()
