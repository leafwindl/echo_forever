# ruff: noqa: ARG001, ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.desktop.infrastructure.bili_scan_worker import (
    _clean_note,
    _coerce_score,
    _instruction,
    _judge,
    _parse_json_object,
)


class BiliScanWorkerRulesTests(unittest.TestCase):
    def test_score_is_clamped(self):
        self.assertEqual(_coerce_score(7), 7.0)
        self.assertEqual(_coerce_score(12), 10.0)
        self.assertEqual(_coerce_score(-3), 0.0)
        self.assertEqual(_coerce_score("bad"), 0.0)

    def test_note_is_cleaned(self):
        self.assertEqual(_clean_note('  "这画面好刺激"  '), "这画面好刺激")

    def test_json_parsing_handles_code_fence(self):
        self.assertEqual(
            _parse_json_object('```json\n{"score": 8, "note": "好看"}\n```'),
            {"score": 8, "note": "好看"},
        )

    def test_instruction_lists_frames(self):
        text = _instruction(
            [
                {
                    "title": "视频A",
                    "frame": "bili_scan_0.png",
                    "score": 8,
                }
            ]
        )
        self.assertIn("视频A", text)
        self.assertIn("bili_scan_0.png", text)


class BiliScanWorkerJudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_judge_sorts_and_skips_missing_verdict(self):
        async def fake_judge_one(item):
            if item["title"] == "bad":
                return None
            return {"score": item["score"], "note": item["note"]}

        items = [
            {"title": "low", "frame": r"C:\EchoComputer\images\a.png", "score": 3, "note": "x"},
            {"title": "bad", "frame": r"C:\EchoComputer\images\b.png", "score": 9, "note": "y"},
            {"title": "high", "frame": r"C:\EchoComputer\images\c.png", "score": 8, "note": "好"},
        ]
        with patch(
            "features.desktop.infrastructure.bili_scan_worker._judge_one",
            new=fake_judge_one,
        ):
            scored = await _judge(items)

        self.assertEqual([row["title"] for row in scored], ["high", "low"])
        self.assertEqual(scored[0]["frame"], "c.png")


if __name__ == "__main__":
    unittest.main()
