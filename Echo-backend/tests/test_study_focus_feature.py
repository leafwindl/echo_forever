import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.domain.entities import ChatHistoryMessage, ExternalAssistantDelivery
from features.letters.application.assemble_context import LetterContextAssembler
from features.study_focus.domain.entities import StudyFocusSession
from features.study_focus.infrastructure import postgres_repository as repository_module
from features.study_focus.interface import router as router_module
from features.study_focus.interface.schemas import StudyFocusUpdateRequest
from shared.interface.dependencies import CurrentUser


def _session(*, status="completed", completion_message_id=None):
    return StudyFocusSession(
        session_id="focus-1",
        user_id="user-a",
        activity_type="阅读",
        short_goal="完成一节",
        planned_duration_seconds=1500,
        actual_duration_seconds=1500,
        status=status,
        started_at=datetime(2026, 8, 11, 9, tzinfo=UTC),
        timezone="Asia/Shanghai",
        ended_at=datetime(2026, 8, 11, 9, 25, tzinfo=UTC),
        completion_message_id=completion_message_id,
    )


class StudyFocusDomainTests(unittest.TestCase):
    def test_state_transitions_allow_pause_resume_and_terminal_states_only(self):
        self.assertTrue(repository_module._transition_allowed("running", "paused"))
        self.assertTrue(repository_module._transition_allowed("paused", "running"))
        self.assertTrue(repository_module._transition_allowed("running", "completed"))
        self.assertTrue(repository_module._transition_allowed("paused", "ended_early"))
        self.assertFalse(repository_module._transition_allowed("completed", "running"))
        self.assertFalse(repository_module._transition_allowed("ended_early", "paused"))

    def test_update_query_scopes_session_to_current_user(self):
        cursor = _Cursor([None])
        connection = _Connection(cursor)
        with patch.object(repository_module, "transaction", return_value=_Transaction(connection)):
            result = repository_module.PostgresStudyFocusRepository().update_session(
                user_id="user-a",
                session_id="focus-owned-by-someone-else",
                status="paused",
                actual_duration_seconds=10,
                occurred_at=datetime(2026, 8, 11, 9, tzinfo=UTC),
            )

        self.assertIsNone(result)
        self.assertEqual(
            cursor.calls[0][1],
            ("user-a", "focus-owned-by-someone-else"),
        )

    def test_create_rejects_conflicting_session_id_from_another_user(self):
        row = {"user_id": "user-b"}
        cursor = _Cursor([row])
        connection = _Connection(cursor)
        with (
            patch.object(repository_module, "transaction", return_value=_Transaction(connection)),
            patch.object(repository_module, "ensure_user_identity"),
            self.assertRaisesRegex(ValueError, "unavailable"),
        ):
            repository_module.PostgresStudyFocusRepository().create_session(
                user_id="user-a",
                session_id="focus-1",
                activity_type="阅读",
                short_goal="",
                planned_duration_seconds=1500,
                started_at=datetime(2026, 8, 11, 9, tzinfo=UTC),
                timezone="Asia/Shanghai",
            )


class CompletionDeliveryTests(unittest.TestCase):
    def test_completed_session_delivers_one_idempotent_congratulation(self):
        current = _session()
        repository = _FakeRouterRepository(current)
        deliveries = []
        message = ChatHistoryMessage(
            message_id=77,
            stable_message_id="msg-77",
            client_message_id="focus_completion:focus-1",
            role="assistant",
            message_type="text",
            content="这一轮完成了，先休息一下吧。",
            content_parts=(),
            created_at=current.ended_at,
        )

        async def deliver(**kwargs):
            deliveries.append(kwargs)
            return ExternalAssistantDelivery(
                conversation_id="conversation-1",
                message=message,
            )

        request = StudyFocusUpdateRequest(
            status="completed",
            actual_duration_seconds=1500,
            occurred_at=current.ended_at,
        )
        with (
            patch.object(router_module, "repository", repository),
            patch.object(router_module, "deliver_external_assistant_message", deliver),
        ):
            first = asyncio.run(
                router_module.update_session("focus-1", request, CurrentUser("user-a"))
            )
            second = asyncio.run(
                router_module.update_session("focus-1", request, CurrentUser("user-a"))
            )

        self.assertEqual(len(deliveries), 1)
        self.assertEqual(repository.marked_message_ids, [77])
        self.assertEqual(first.completion_message_id, 77)
        self.assertEqual(second.completion_message_id, 77)

    def test_early_ended_session_delivers_a_gentle_check_in_once(self):
        current = _session(status="ended_early")
        repository = _FakeRouterRepository(current)
        deliveries = []
        message = ChatHistoryMessage(
            message_id=78,
            stable_message_id="msg-78",
            client_message_id="focus_ended_early:focus-1",
            role="assistant",
            message_type="text",
            content="你刚刚学习了 25 分钟。是有其他事情要忙吗？",
            content_parts=(),
            created_at=current.ended_at,
        )

        async def deliver(**kwargs):
            deliveries.append(kwargs)
            return ExternalAssistantDelivery(
                conversation_id="conversation-1",
                message=message,
            )

        request = StudyFocusUpdateRequest(
            status="ended_early",
            actual_duration_seconds=1500,
            occurred_at=current.ended_at,
        )
        with (
            patch.object(router_module, "repository", repository),
            patch.object(router_module, "deliver_external_assistant_message", deliver),
        ):
            result = asyncio.run(
                router_module.update_session("focus-1", request, CurrentUser("user-a"))
            )

        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["source"], "focus_ended_early")
        self.assertIn("有其他事情要忙吗", deliveries[0]["content"])
        self.assertEqual(result.completion_message_id, 78)


class DailyLetterEvidenceTests(unittest.TestCase):
    def test_focus_evidence_is_fact_based_and_summarized(self):
        sessions = [
            _session(),
            StudyFocusSession(
                session_id="focus-2",
                user_id="user-a",
                activity_type="刷题",
                short_goal="",
                planned_duration_seconds=600,
                actual_duration_seconds=420,
                status="ended_early",
                started_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
                timezone="Asia/Shanghai",
                ended_at=datetime(2026, 8, 11, 10, 7, tzinfo=UTC),
            ),
        ]

        evidence = LetterContextAssembler._build_focus_evidence(sessions)
        snapshot = LetterContextAssembler._focus_snapshot(sessions)

        self.assertIn("[STUDY_FOCUS_EVIDENCE]", evidence)
        self.assertIn("focus_session_id=focus-1", evidence)
        self.assertIn("actual_seconds=420", evidence)
        self.assertIn("不能据此断言具体学习目标已经完成", evidence)
        self.assertEqual(snapshot["session_count"], 2)
        self.assertEqual(snapshot["total_actual_duration_seconds"], 1920)
        self.assertEqual(snapshot["completed_count"], 1)
        self.assertEqual(snapshot["ended_early_count"], 1)


class _FakeRouterRepository:
    def __init__(self, session):
        self.session = session
        self.marked_message_ids = []

    def update_session(self, **_kwargs):
        return self.session

    def mark_completion_message(self, *, message_id, **_kwargs):
        self.marked_message_ids.append(message_id)
        self.session = StudyFocusSession(
            **{**self.session.__dict__, "completion_message_id": message_id}
        )
        return self.session


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
