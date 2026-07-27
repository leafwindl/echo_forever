import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.relationship.application.relationship_management import (
    RelationshipManagementService,
)
from features.relationship.domain.entities import (
    RelationshipSignal,
    RelationshipState,
    default_relationship_state,
)
from features.relationship.domain.rules import (
    advance_relationship_state,
    build_relationship_context,
    calculate_relationship_score,
    detect_relationship_signals,
    infer_interaction_warmth,
    resolve_relationship_stage,
)


class InMemoryRelationshipRepository:
    def __init__(self):
        self.state = default_relationship_state("user-a")
        self.saved_signals: tuple[RelationshipSignal, ...] = ()
        self.source_message_id = None
        self.memory_count = 2

    def get_or_create(self, user_id):
        return self.state

    def count_active_memories(self, user_id):
        return self.memory_count

    def save_progress(self, state, signals, source_message_id):
        self.state = state
        self.saved_signals = signals
        self.source_message_id = source_message_id
        return state

    def reset(self, user_id):
        self.state = default_relationship_state(user_id)
        return self.state


class RelationshipRuleTests(unittest.TestCase):
    def test_message_volume_alone_cannot_bypass_active_day_gate(self):
        state = RelationshipState(
            user_id="user-a",
            interaction_turns=500,
            active_days=1,
            shared_memory_count=20,
        )
        state = RelationshipState(**{**state.__dict__, "score": calculate_relationship_score(state)})

        self.assertEqual("new", resolve_relationship_stage(state, "natural"))

    def test_relationship_stage_uses_pace_and_requires_explicit_close_signal(self):
        trusted = RelationshipState(
            user_id="user-a",
            stage="new",
            score=90,
            active_days=21,
            explicit_relation_signal_count=0,
        )
        close = RelationshipState(
            user_id="user-a",
            stage="new",
            score=90,
            active_days=30,
            explicit_relation_signal_count=1,
        )

        self.assertEqual("trusted", resolve_relationship_stage(trusted, "natural"))
        self.assertEqual("close", resolve_relationship_stage(close, "natural"))
        self.assertEqual("close", resolve_relationship_stage(close, "slow"))

    def test_open_pace_changes_threshold_but_not_current_evidence(self):
        state = RelationshipState(user_id="user-a", score=22, active_days=2)

        self.assertEqual("new", resolve_relationship_stage(state, "natural"))
        self.assertEqual("familiar", resolve_relationship_stage(state, "open"))

    def test_explicit_boundary_immediately_restrains_affection_and_warmth(self):
        state = RelationshipState(
            user_id="user-a",
            stage="close",
            affection_permission="welcomed",
        )
        context = build_relationship_context(
            state,
            "别再叫我宝贝了",
            relationship_pace="natural",
            affection_style="expressive",
        )

        self.assertEqual("reserved", context.interaction_warmth)
        self.assertEqual("restrained", context.effective_affection_style)
        self.assertEqual("close", context.state.stage)

    def test_positive_share_is_warm_without_becoming_relationship_signal(self):
        self.assertEqual("warm", infer_interaction_warmth("今天打球赢了，挺开心的"))
        self.assertEqual((), detect_relationship_signals("今天打球赢了，挺开心的"))

    def test_advance_records_active_day_and_explicit_permission(self):
        progress = advance_relationship_state(
            default_relationship_state("user-a"),
            observed_date="2026-07-27",
            observed_at="2026-07-27T10:00:00+00:00",
            shared_memory_count=3,
            user_message="我喜欢你，以后可以叫我小叶",
            relationship_pace="natural",
        )

        self.assertEqual(1, progress.state.interaction_turns)
        self.assertEqual(1, progress.state.active_days)
        self.assertEqual("welcomed", progress.state.affection_permission)
        self.assertEqual(1, progress.state.explicit_relation_signal_count)
        self.assertIn("active_day", {signal.event_type for signal in progress.signals})


class RelationshipManagementTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRelationshipRepository()
        self.service = RelationshipManagementService(self.repository)

    def test_record_turn_persists_structured_signals_without_raw_message(self):
        state = self.service.record_turn(
            "user-a",
            "谢谢你陪我",
            source_message_id=42,
            relationship_pace="natural",
        )

        self.assertEqual(1, state.interaction_turns)
        self.assertEqual(42, self.repository.source_message_id)
        self.assertIn(
            "positive_relation",
            {signal.event_type for signal in self.repository.saved_signals},
        )

    def test_reset_keeps_other_user_data_out_of_scope(self):
        reset = self.service.reset("user-a")

        self.assertEqual("user-a", reset.user_id)
        self.assertEqual("new", reset.stage)
        self.assertEqual(0, reset.score)


if __name__ == "__main__":
    unittest.main()
