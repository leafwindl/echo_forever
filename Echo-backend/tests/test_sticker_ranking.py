import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from features.stickers.infrastructure.postgres_repository import rank_sticker_rows  # noqa: E402

from scripts.sync_echo_stickers import scan_assets  # noqa: E402


def _row(
    sticker_id: str,
    priority: int,
    tag: str = "开心",
    owner_type: str = "echo",
) -> dict[str, object]:
    return {
        "sticker_id": sticker_id,
        "owner_type": owner_type,
        "semantic_tags": [tag],
        "description": "",
        "priority": priority,
        "created_at": datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
    }


class StickerRankingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 7, 13, 0, tzinfo=UTC)
        self.rows = [_row("stk_high", 300), _row("stk_mid", 200), _row("stk_low", 100)]

    def _rank(self, *, recent_ids=None, last_used=None):
        return rank_sticker_rows(
            self.rows,
            terms=("开心",),
            purpose="proactive",
            recent_ids=set(recent_ids or ()),
            last_used=dict(last_used or {}),
            now=self.now,
            cooldown=timedelta(minutes=5),
        )

    def test_priority_orders_semantically_equivalent_candidates(self):
        self.assertEqual([row["sticker_id"] for row in self._rank()], [
            "stk_high",
            "stk_mid",
            "stk_low",
        ])

    def test_recent_turn_and_time_cooldowns_select_next_candidate(self):
        ranked = self._rank(
            recent_ids={"stk_high"},
            last_used={"stk_mid": self.now - timedelta(minutes=2)},
        )
        self.assertEqual(ranked[0]["sticker_id"], "stk_low")

    def test_all_candidates_cooling_falls_back_to_highest_priority(self):
        ranked = self._rank(recent_ids={"stk_high", "stk_mid", "stk_low"})
        self.assertEqual(ranked[0]["sticker_id"], "stk_high")

    def test_official_sticker_gets_small_bonus_on_semantic_tie(self):
        self.rows = [
            _row("stk_private", 100, owner_type="user"),
            _row("stk_official", 100, owner_type="echo"),
        ]

        ranked = self._rank()

        self.assertEqual(ranked[0]["sticker_id"], "stk_official")

    def test_private_sticker_can_beat_weaker_official_match(self):
        self.rows = [
            _row("stk_private", 100, tag="开心", owner_type="user"),
            _row("stk_official", 100, tag="很开心", owner_type="echo"),
        ]

        ranked = self._rank()

        self.assertEqual(ranked[0]["sticker_id"], "stk_private")


class EchoStickerAssetTests(unittest.TestCase):
    def test_filename_becomes_semantic_tag(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "开心.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\ncontent")
            assets = scan_assets(Path(directory))
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].semantic_tag, "开心")
        self.assertEqual(assets[0].content_type, "image/png")

    def test_duplicate_content_is_rejected_before_upload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"\xff\xd8\xffcontent"
            (root / "开心.jpg").write_bytes(content)
            (root / "嘿嘿.jpg").write_bytes(content)
            with self.assertRaises(ValueError):
                scan_assets(root)
