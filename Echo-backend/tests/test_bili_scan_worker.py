# ruff: noqa: ARG001, ARG002
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.desktop.infrastructure.bili_scan_worker import (
    NOTIFY_TOOL_SCOPE,
    _clean_note,
    _coerce_score,
    _instruction,
    _is_noise_title,
    _judge,
    _notify_completed,
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
        self.assertIn("第 1/3 轮", text)

    def test_noise_titles_are_filtered(self):
        for title in ("添加至稍后再看153.3万", "10:15", "12.3万", "短"):
            with self.subTest(title=title):
                self.assertTrue(_is_noise_title(title))
        self.assertFalse(_is_noise_title("旦角戏腔版《新·与天齐》"))


class BiliScanNotifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_scope_allows_self_decided_scan(self):
        reply = SimpleNamespace(
            reply_segments=("刷完了",),
            reply_text="",
            tool_results=(),
        )
        with (
            patch(
                "features.chat.public.generate_proactive_action",
                new=AsyncMock(return_value=reply),
            ) as generate,
            patch(
                "features.desktop.public.send_wechat_message",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "features.chat.public.deliver_external_assistant_message",
                new=AsyncMock(),
            ) as history_sink,
        ):
            await _notify_completed(
                {
                    "job_id": "j1",
                    "user_id": "u1",
                    "conversation_id": "c1",
                    "round": 1,
                },
                {"items": [{"title": "视频A", "frame": "f.png", "score": 8}]},
            )

        scope = generate.await_args.kwargs["tool_scope"]
        self.assertEqual(scope, NOTIFY_TOOL_SCOPE)
        self.assertIn("bili_browse", scope)
        self.assertIn("bili_share", scope)
        instruction = generate.await_args.kwargs["instruction"]
        self.assertIn("第 1/3 轮", instruction)
        history_sink.assert_awaited_once()

    async def test_last_round_forbids_another_scan(self):
        reply = SimpleNamespace(reply_segments=("刷够了",), reply_text="", tool_results=())
        with (
            patch(
                "features.chat.public.generate_proactive_action",
                new=AsyncMock(return_value=reply),
            ) as generate,
            patch(
                "features.desktop.public.send_wechat_message",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "features.chat.public.deliver_external_assistant_message",
                new=AsyncMock(),
            ),
        ):
            await _notify_completed(
                {
                    "job_id": "j2",
                    "user_id": "u1",
                    "conversation_id": "c1",
                    "round": 3,
                },
                {"items": [{"title": "视频A", "frame": "f.png", "score": 8}]},
            )

        instruction = generate.await_args.kwargs["instruction"]
        self.assertIn("第 3/3 轮", instruction)
        self.assertIn("不能再刷", instruction)


class BiliScanWorkerJudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_judge_sorts_and_skips_missing_verdict(self):
        async def fake_judge_one(item):
            if item["title"] == "坏视频素材分享":
                return None
            return {"score": item["score"], "note": item["note"]}

        items = [
            {
                "title": "低分视频推荐",
                "frame": r"C:\EchoComputer\images\a.png",
                "score": 3,
                "note": "x",
            },
            {
                "title": "坏视频素材分享",
                "frame": r"C:\EchoComputer\images\b.png",
                "score": 9,
                "note": "y",
            },
            {
                "title": "高分视频推荐",
                "frame": r"C:\EchoComputer\images\c.png",
                "score": 8,
                "note": "好",
            },
        ]
        with patch(
            "features.desktop.infrastructure.bili_scan_worker._judge_one",
            new=fake_judge_one,
        ):
            scored = await _judge(items)

        self.assertEqual([row["title"] for row in scored], ["高分视频推荐", "低分视频推荐"])
        self.assertEqual(scored[0]["frame"], "c.png")


if __name__ == "__main__":
    unittest.main()
