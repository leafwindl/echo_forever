import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.relationship.domain.affection import (
    cap_daily_delta,
    clamp_affection,
    stage_for_affection,
    validate_adjustment,
)
from features.relationship.domain.rules import next_requestable_stage


class AffectionRuleTests(unittest.TestCase):
    def test_single_adjustment_bounds_and_reason(self):
        self.assertEqual((5, "真诚分享"), validate_adjustment(5, " 真诚分享 "))
        for delta in (0, 11, -11):
            with self.assertRaises(ValueError):
                validate_adjustment(delta, "x")
        with self.assertRaises(ValueError):
            validate_adjustment(5, "  ")
        with self.assertRaises(ValueError):
            validate_adjustment(5, "x" * 121)

    def test_daily_net_limit_applies_to_both_directions(self):
        self.assertEqual(5, cap_daily_delta(10, 25))
        self.assertEqual(0, cap_daily_delta(10, 30))
        self.assertEqual(-5, cap_daily_delta(-10, -25))
        self.assertEqual(0, cap_daily_delta(-10, -30))
        self.assertEqual(10, cap_daily_delta(10, 0))
        self.assertEqual(-10, cap_daily_delta(-10, 0))

    def test_affection_clamp_and_stage_thresholds(self):
        self.assertEqual(1, clamp_affection(-20))
        self.assertEqual(1000, clamp_affection(1200))
        self.assertEqual("new", stage_for_affection(99))
        self.assertEqual("familiar", stage_for_affection(100))
        self.assertEqual("ambiguous", stage_for_affection(300))
        self.assertEqual("lover", stage_for_affection(500))
        self.assertEqual("beloved", stage_for_affection(800))

    def test_stage_request_eligibility_and_auto_familiar(self):
        self.assertEqual("", next_requestable_stage("new", 100))
        self.assertEqual("", next_requestable_stage("familiar", 299))
        self.assertEqual("ambiguous", next_requestable_stage("familiar", 300))
        self.assertEqual("lover", next_requestable_stage("ambiguous", 500))
        self.assertEqual("beloved", next_requestable_stage("lover", 800))
        self.assertEqual("", next_requestable_stage("beloved", 1000))


if __name__ == "__main__":
    unittest.main()
