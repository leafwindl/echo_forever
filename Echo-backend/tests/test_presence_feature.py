# ruff: noqa: ARG002

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.presence.application.presence_service import PresenceService
from features.presence.domain.entities import (
    PresenceContext,
    PresenceMemory,
    PresenceMessage,
    PresenceState,
    PresenceStatus,
    PresenceThought,
    ThoughtDraft,
)


class FakeRepository:
    def __init__(self, state: PresenceState | None = None):
        self.state = state or PresenceState(user_id="user-1")
        self.thoughts: list[PresenceThought] = []
        self.events: list[str] = []

    def get_or_create_state(self, user_id):
        if self.state.user_id != user_id:
            self.state = PresenceState(user_id=user_id)
        return self.state

    def save_state(self, state):
        self.state = state

    def recent_thoughts(self, user_id, limit):
        return self.thoughts[-limit:]

    def add_thought(self, thought):
        self.thoughts.append(thought)

    def record_event(self, *, user_id, event_type, detail, now):
        self.events.append(event_type)


class FakeContext:
    def __init__(self, last_user_at, text="今天有点累"):
        self.last_user_at = last_user_at
        self.text = text

    async def load(self, user_id, limit):
        message = PresenceMessage(role="user", content=self.text, created_at=self.last_user_at)
        return PresenceContext(
            messages=(message,),
            last_user_message_at=self.last_user_at,
            last_user_text=self.text,
            recent_assistant_text="先歇一会儿吧",
        )

    def recent_user_ids(self, limit):
        return ("user-1",)


class FakeMemory:
    async def recall(self, user_id, query):
        return PresenceMemory(memory_id="mem-1", content="她说过最近总加班", importance=4)


class FakeGenerator:
    def __init__(self, draft: ThoughtDraft | None = None):
        self.draft = draft or ThoughtDraft(text="也许她今天只是需要安静一会儿", salience=0.7)
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        return self.draft


class FakeQuiet:
    def __init__(self, quiet=False):
        self.quiet = quiet

    def is_quiet(self, user_id, now):
        return self.quiet


class FakeComposer:
    def __init__(self, text="给你留了句话"):
        self.text = text

    async def compose(self, **kwargs):
        return self.text


class FakeDelivery:
    def __init__(self):
        self.delivered: list[tuple[str, str]] = []

    async def deliver(self, *, user_id, thought_id, text):
        self.delivered.append((user_id, text))
        return True


def _service(
    repository,
    context,
    generator=None,
    quiet=None,
    composer=None,
    delivery=None,
    **overrides,
):
    values = {
        "active_window_minutes": 5,
        "silence_minutes": 30,
        "min_thought_interval_minutes": 45,
        "daily_thought_budget": 8,
        "proactive_message_budget": 3,
        "proactive_message_interval_minutes": 120,
        "context_messages": 8,
        "max_candidate_users": 20,
    }
    values.update(overrides)
    return PresenceService(
        repository=repository,
        context_source=context,
        memory_source=FakeMemory(),
        thought_generator=generator or FakeGenerator(),
        message_composer=composer or FakeComposer(),
        message_delivery=delivery or FakeDelivery(),
        quiet_hours=quiet or FakeQuiet(),
        **values,
    )


class PresenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_user_is_skipped(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(minutes=1)))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "skipped")
        self.assertEqual(result.reason, "user_active")
        self.assertEqual(repository.state.status, PresenceStatus.ACTIVE)

    async def test_quiet_hours_are_skipped(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(hours=2)), quiet=FakeQuiet(True))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "quiet_hours")
        self.assertEqual(repository.state.status, PresenceStatus.SLEEPING)

    async def test_recent_silence_is_skipped(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(minutes=10)))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "too_recent")
        self.assertEqual(repository.thoughts, [])

    async def test_daily_budget_is_enforced(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                thoughts_used=8,
                thought_budget_date=now.date(),
            )
        )
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "daily_budget")

    async def test_thought_cooldown_is_enforced(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                last_thought_at=now - timedelta(minutes=10),
                thought_budget_date=now.date(),
            )
        )
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "thought_cooldown")

    async def test_eligible_user_creates_one_thought(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        generator = FakeGenerator()
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
        )
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "thought")
        self.assertIsNotNone(result.thought)
        self.assertEqual(len(repository.thoughts), 1)
        self.assertEqual(repository.state.thoughts_used, 1)
        self.assertEqual(repository.state.last_decision, "thought")

    async def test_shareable_thought_delivers_one_message(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        delivery = FakeDelivery()
        generator = FakeGenerator(
            ThoughtDraft(text="想起上次说的事", salience=0.7, shareable=True)
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            composer=FakeComposer("上次说的事后来怎么样了？"),
            delivery=delivery,
        )
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "message")
        self.assertEqual(result.message_text, "上次说的事后来怎么样了？")
        self.assertEqual(len(delivery.delivered), 1)
        self.assertEqual(repository.state.proactive_messages_used, 1)
        self.assertEqual(repository.state.last_decision, "message")

    async def test_proactive_message_budget_blocks_extra_messages(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                proactive_messages_used=3,
                proactive_budget_date=now.date(),
                thought_budget_date=now.date(),
            )
        )
        delivery = FakeDelivery()
        generator = FakeGenerator(
            ThoughtDraft(text="又想起一件事", salience=0.7, shareable=True)
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            composer=FakeComposer("想跟你说件事"),
            delivery=delivery,
        )
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "thought")
        self.assertEqual(delivery.delivered, [])

    async def test_duplicate_thought_is_not_stored(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        repository.thoughts.append(
            PresenceThought(
                thought_id="old",
                user_id="user-1",
                text="也许她今天只是需要安静一会儿",
                salience=0.7,
                shareable=False,
            )
        )
        generator = FakeGenerator(ThoughtDraft(text="也许她今天只是需要安静一会儿", salience=0.7))
        service = _service(repository, FakeContext(now - timedelta(hours=2)), generator=generator)
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "duplicate_thought")
        self.assertEqual(len(repository.thoughts), 1)

    async def test_run_once_processes_recent_users(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        created = await service.run_once(now=now)
        self.assertEqual(created, 1)
        self.assertEqual(repository.state.user_id, "user-1")


if __name__ == "__main__":
    unittest.main()
