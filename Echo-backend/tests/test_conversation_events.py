# ruff: noqa: ARG002
from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.postgres_schema import build_postgres_schema_text
from features.conversation_events.application.record_event import RecordConversationEvent
from features.conversation_events.domain.entities import (
    ACTOR_ECHO,
    EVENT_MESSAGE,
    EVENT_TOOL_CALL,
    ConversationEvent,
)
from features.conversation_events.public import (
    list_conversation_events,
    record_conversation_event,
)


class FakeRepository:
    def __init__(self):
        self.events: list[ConversationEvent] = []

    def append(self, event):
        self.events.append(event)
        return len(self.events)

    def list_for_conversation(self, *, user_id, conversation_id, limit=50):
        return list(self.events)


class RecordEventTests(unittest.TestCase):
    def test_use_case_appends_event(self):
        repo = FakeRepository()
        event = ConversationEvent(
            event_type=EVENT_MESSAGE,
            source="app_chat",
            actor=ACTOR_ECHO,
            user_id="u1",
            conversation_id="c1",
            content="hi",
        )

        event_id = RecordConversationEvent(repo).execute(event)

        self.assertEqual(event_id, 1)
        self.assertEqual(repo.events[0], event)

    def test_public_records_all_fields(self):
        repo = FakeRepository()
        now = datetime.now(UTC)
        with patch(
            "features.conversation_events.public._repository",
            return_value=repo,
        ):
            record_conversation_event(
                event_type=EVENT_TOOL_CALL,
                source="agent",
                actor=ACTOR_ECHO,
                user_id="u1",
                conversation_id="c1",
                turn_id="run_1",
                content="computer_exec completed",
                payload={"tool_name": "computer_exec"},
                source_created_at=now,
            )

        event = repo.events[0]
        self.assertEqual(event.event_type, EVENT_TOOL_CALL)
        self.assertEqual(event.source, "agent")
        self.assertEqual(event.turn_id, "run_1")
        self.assertEqual(event.payload, {"tool_name": "computer_exec"})
        self.assertEqual(event.source_created_at, now)

    def test_public_lists_events(self):
        repo = FakeRepository()
        repo.append(
            ConversationEvent(
                event_type=EVENT_MESSAGE,
                source="wechat",
                actor=ACTOR_ECHO,
                user_id="u1",
                conversation_id="c1",
                content="hi",
            )
        )
        with patch(
            "features.conversation_events.public._repository",
            return_value=repo,
        ):
            events = list_conversation_events(user_id="u1", conversation_id="c1")

        self.assertEqual([event.content for event in events], ["hi"])

    def test_event_payload_defaults_are_isolated(self):
        first = ConversationEvent(
            event_type=EVENT_MESSAGE,
            source="app_chat",
            actor=ACTOR_ECHO,
            user_id="u1",
        )
        second = ConversationEvent(
            event_type=EVENT_MESSAGE,
            source="app_chat",
            actor=ACTOR_ECHO,
            user_id="u2",
        )

        self.assertEqual(first.payload, {})
        self.assertIsNot(first.payload, second.payload)


class ConversationEventSchemaTests(unittest.TestCase):
    def test_schema_creates_event_table_and_indexes(self):
        schema = build_postgres_schema_text(3)

        self.assertIn("CREATE TABLE IF NOT EXISTS conversation_events", schema)
        self.assertIn("idx_conversation_events_user_created", schema)
        self.assertIn("idx_conversation_events_conversation", schema)


if __name__ == "__main__":
    unittest.main()
