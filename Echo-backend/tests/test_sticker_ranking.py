import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from features.stickers.infrastructure.postgres_repository import (  # noqa: E402
    filter_semantically_close_rows,
    rank_sticker_rows,
    sticker_row_visible_to_user,
)

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

    def _rank(self):
        return rank_sticker_rows(
            self.rows,
            terms=("开心",),
        )

    def test_priority_orders_semantically_equivalent_candidates(self):
        self.assertEqual(
            [row["sticker_id"] for row in self._rank()],
            [
                "stk_high",
                "stk_mid",
                "stk_low",
            ],
        )

    def test_repeated_search_keeps_the_best_match_available(self):
        first = self._rank()
        second = self._rank()
        self.assertEqual(first, second)
        self.assertEqual(second[0]["sticker_id"], "stk_high")

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

    def test_compound_query_can_boost_an_embedded_known_tag(self):
        self.rows = [
            _row("stk_encourage", 100, tag="加油"),
            _row("stk_happy", 100, tag="开心"),
        ]

        ranked = rank_sticker_rows(
            self.rows,
            terms=("辛苦了加油",),
        )

        self.assertEqual(ranked[0]["sticker_id"], "stk_encourage")

    def test_private_sticker_visibility_is_scoped_to_owner(self):
        official = {"owner_type": "echo", "owner_user_id": None}
        user_a = {"owner_type": "user", "owner_user_id": "user_a"}

        self.assertTrue(sticker_row_visible_to_user(official, "user_b"))
        self.assertTrue(sticker_row_visible_to_user(user_a, "user_a"))
        self.assertFalse(sticker_row_visible_to_user(user_a, "user_b"))

    def test_vector_candidates_keep_only_semantically_close_alternatives(self):
        rows = [
            {"sticker_id": "best", "similarity_score": 0.72},
            {"sticker_id": "similar", "similarity_score": 0.70},
            {"sticker_id": "unrelated", "similarity_score": 0.61},
        ]

        filtered = filter_semantically_close_rows(rows, maximum_score_gap=0.04)

        self.assertEqual(
            [row["sticker_id"] for row in filtered],
            ["best", "similar"],
        )


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
