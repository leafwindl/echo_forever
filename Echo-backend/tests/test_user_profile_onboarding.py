import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.user_profile.domain.entities import UserProfile
from features.user_profile.domain.onboarding import evaluate_profile_onboarding


class ProfileOnboardingTests(unittest.TestCase):
    def _empty(self) -> UserProfile:
        return UserProfile(user_id="u1")

    def test_empty_profile_starts_collecting_one_or_two_fields(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            current_conversation_user_turns=1,
            current_message_text="今天好累",
        )
        self.assertEqual("collecting", state.phase)
        self.assertTrue(state.ask_allowed)
        self.assertEqual(("称呼", "职业"), state.missing)

    def test_name_and_basics_finish_onboarding(self):
        state = evaluate_profile_onboarding(
            profile=UserProfile(
                user_id="u1",
                display_name="叶子",
                basics={"职业": "研究生"},
            ),
            current_conversation_user_turns=2,
            current_message_text="今天好累",
        )
        self.assertEqual("done", state.phase)
        self.assertEqual("enough", state.reason)
        self.assertFalse(state.ask_allowed)

    def test_explicit_refusal_finishes_onboarding(self):
        state = evaluate_profile_onboarding(
            profile=UserProfile(user_id="u1", boundaries=("不采集个人资料",)),
            current_conversation_user_turns=1,
            current_message_text="你好",
        )
        self.assertEqual("done", state.phase)
        self.assertEqual("refused", state.reason)

    def test_familiar_relationship_stops_onboarding(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            stage="familiar",
            current_conversation_user_turns=1,
            current_message_text="你好",
        )
        self.assertEqual("done", state.phase)
        self.assertEqual("relationship_stage", state.reason)

    def test_too_many_turns_stops_onboarding(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            interaction_turns=9,
            current_conversation_user_turns=1,
            current_message_text="你好",
        )
        self.assertEqual("done", state.phase)
        self.assertEqual("too_many_turns", state.reason)

    def test_session_limit_pauses_without_asking(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            current_conversation_user_turns=9,
            current_message_text="你好",
        )
        self.assertEqual("paused", state.phase)
        self.assertEqual("session_limit", state.reason)
        self.assertFalse(state.ask_allowed)

    def test_task_message_pauses_collection(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            current_conversation_user_turns=1,
            current_message_text="帮我写个快排",
        )
        self.assertEqual("paused", state.phase)
        self.assertEqual("task_intent", state.reason)
        self.assertFalse(state.ask_allowed)

    def test_recent_assistant_question_pauses_repeat(self):
        state = evaluate_profile_onboarding(
            profile=self._empty(),
            current_conversation_user_turns=2,
            current_message_text="今天好累",
            recent_assistant_texts=("怎么称呼你？",),
        )
        self.assertEqual("paused", state.phase)
        self.assertEqual("recently_asked", state.reason)
        self.assertFalse(state.ask_allowed)

    def test_name_only_keeps_remaining_fields(self):
        state = evaluate_profile_onboarding(
            profile=UserProfile(user_id="u1", display_name="叶子"),
            current_conversation_user_turns=1,
            current_message_text="今天好累",
        )
        self.assertEqual("collecting", state.phase)
        self.assertEqual(("称呼",), state.known)
        self.assertEqual(("职业", "作息"), state.missing)


if __name__ == "__main__":
    unittest.main()
