from __future__ import annotations

import unittest

from features.mobile_agent.application.skills import _first_result_for_query


class AppSkillParsingTests(unittest.TestCase):
    def test_picks_first_visible_song_result(self):
        text = """
        package=com.netease.cloudmusic  class=android.widget.FrameLayout

        晴天  [497,110][812,218]
        单曲  [174,310][240,390]
        晴天 (原唱 周杰伦)  [72,860][1008,980]  CLICK
        晴天 (钢琴版)  [72,1100][1008,1220]  CLICK
        """
        point = _first_result_for_query(text, "晴天")
        self.assertEqual(point, (540, 920))

    def test_ignores_search_box_and_tabs(self):
        text = """
        晴天  [497,110][812,218]
        单曲  [174,310][240,390]
        """
        self.assertIsNone(_first_result_for_query(text, "晴天"))


if __name__ == "__main__":
    unittest.main()
