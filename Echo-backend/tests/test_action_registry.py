from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.action_registry import (
    ACTION_SPECS,
    get_action_spec,
    parse_action_kind,
)


class ActionRegistryTests(unittest.TestCase):
    def test_kinds_are_unique(self):
        kinds = [spec.kind for spec in ACTION_SPECS]
        self.assertEqual(len(kinds), len(set(kinds)))

    def test_bili_scope_has_scan_and_share(self):
        spec = get_action_spec("bili")
        self.assertIsNotNone(spec)
        self.assertIn("bili_browse", spec.tool_scope)
        self.assertIn("bili_share", spec.tool_scope)

    def test_unknown_action_returns_none(self):
        self.assertIsNone(get_action_spec("camera"))

    def test_parse_action_kind(self):
        self.assertEqual(parse_action_kind("music:晴天"), "music")
        self.assertEqual(parse_action_kind("no-colon"), "")


if __name__ == "__main__":
    unittest.main()
