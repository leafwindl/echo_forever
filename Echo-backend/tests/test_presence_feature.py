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
        self.draft = draft or ThoughtDraft(
            text="也许她今天只是需要安静一会儿",
            salience=0.7,
        )
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        return self.draft


class FakeQuiet:
    def __init__(self, quiet=False):
        self.quiet = quiet

    def is_quiet(self, user_id, now):
        return self.quiet

    def can_send_spontaneous(self, user_id, now):
        return not self.quiet


class FakeGoalCreator:
    def __init__(self):
        self.goals: list[tuple[str, str]] = []

    def create_goal(
        self,
        *,
        user_id,
        intent,
        draft_text,
        trigger_type="presence",
        trigger_ref="",
        action_intent="",
        plan="",
    ):
        self.goals.append((user_id, draft_text, action_intent))
        return f"goal_{len(self.goals)}"


class FakeMemoryWriter:
    def __init__(self):
        self.written: list[tuple[str, float]] = []

    async def remember(self, *, user_id, text, salience):
        self.written.append((text, salience))
        return "mem_test"


def _service(
    repository,
    context,
    generator=None,
    quiet=None,
    goal_creator=None,
    **overrides,
):
    values = {
        "active_window_minutes": 5,
        "silence_minutes": 30,
        "min_thought_interval_minutes": 45,
        "daily_thought_budget": 8,
        "message_min_salience": 0.3,
        "memory_salience_threshold": 0.7,
        "context_messages": 8,
        "max_candidate_users": 20,
    }
    values.update(overrides)
    return PresenceService(
        repository=repository,
        context_source=context,
        memory_source=FakeMemory(),
        thought_generator=generator or FakeGenerator(),
        goal_creator=goal_creator or FakeGoalCreator(),
        memory_writer=FakeMemoryWriter(),
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

    async def test_two_unanswered_outreaches_downshift_future_messages(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                last_proactive_message_at=now - timedelta(hours=3),
                outreach_sent_count=1,
                consecutive_unanswered=1,
                thought_budget_date=now.date(),
            )
        )
        generator = FakeGenerator(
            ThoughtDraft(text="又想起他上次说的事", salience=0.5, shareable=True)
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=4)),
            generator=generator,
        )
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "thought")
        self.assertEqual(repository.state.consecutive_unanswered, 2)
        self.assertIsNotNone(repository.state.outreach_downshift_until)

    async def test_action_intent_creates_goal_instead_of_direct_execution(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        creator = FakeGoalCreator()
        generator = FakeGenerator(
            ThoughtDraft(
                text="外面在放歌，想给他放一首晴天",
                salience=0.6,
                shareable=True,
                action_intent="music:晴天",
            )
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            goal_creator=creator,
        )
        await service.tick("user-1", now=now)
        self.assertEqual(len(creator.goals), 1)
        self.assertEqual(creator.goals[0][2], "music:晴天")

    async def test_high_salience_thought_is_written_to_memory(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        writer = FakeMemoryWriter()
        generator = FakeGenerator(
            ThoughtDraft(text="他说最近总睡不好，我记着这件事", salience=0.8)
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
        )
        service.memory_writer = writer
        await service.tick("user-1", now=now)
        self.assertEqual(writer.written, [("他说最近总睡不好，我记着这件事", 0.8)])

    async def test_shareable_thought_delivers_one_message(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        creator = FakeGoalCreator()
        generator = FakeGenerator(
            ThoughtDraft(
                text="想起上次说的事",
                salience=0.7,
                shareable=True,
                draft_text="上次说的事后来怎么样了？",
            )
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            goal_creator=creator,
        )
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.decision, "message")
        self.assertEqual(result.message_text, "上次说的事后来怎么样了？")
        self.assertEqual(len(creator.goals), 1)
        self.assertEqual(repository.state.proactive_messages_used, 1)
        self.assertEqual(repository.state.last_decision, "message")

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

    async def test_not_due_is_skipped(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                next_tick_at=now + timedelta(minutes=10),
            )
        )
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        result = await service.tick("user-1", now=now)
        self.assertEqual(result.reason, "not_due")
        self.assertEqual(repository.thoughts, [])

    async def test_next_tick_is_scheduled_after_thought(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        await service.tick("user-1", now=now)
        self.assertIsNotNone(repository.state.next_tick_at)
        self.assertGreater(repository.state.next_tick_at, now)

    async def test_action_request_is_routed_to_registered_action(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        creator = FakeGoalCreator()
        generator = FakeGenerator(
            ThoughtDraft(
                text="想看看B站今天有什么",
                salience=0.6,
                action_request="想看看B站",
            )
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            goal_creator=creator,
        )
        await service.tick("user-1", now=now)
        self.assertEqual(len(creator.goals), 1)
        self.assertTrue(creator.goals[0][2].startswith("bili:"))

    async def test_unavailable_action_request_records_gap(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        creator = FakeGoalCreator()
        generator = FakeGenerator(
            ThoughtDraft(
                text="想变成一只猫",
                salience=0.6,
                action_request="想变成一只猫",
            )
        )
        service = _service(
            repository,
            FakeContext(now - timedelta(hours=2)),
            generator=generator,
            goal_creator=creator,
        )
        await service.tick("user-1", now=now)
        self.assertEqual(creator.goals, [])
        self.assertIn("action_unavailable", repository.events)

    async def test_downshift_extends_next_tick(self):
        now = datetime.now(UTC)
        repository = FakeRepository(
            PresenceState(
                user_id="user-1",
                outreach_downshift_until=now + timedelta(days=1),
            )
        )
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        await service.tick("user-1", now=now)
        self.assertGreaterEqual(
            repository.state.next_tick_at,
            now + timedelta(minutes=179),
        )

    async def test_run_once_processes_recent_users(self):
        now = datetime.now(UTC)
        repository = FakeRepository()
        service = _service(repository, FakeContext(now - timedelta(hours=2)))
        created = await service.run_once(now=now)
        self.assertEqual(created, 1)
        self.assertEqual(repository.state.user_id, "user-1")


if __name__ == "__main__":
    unittest.main()
