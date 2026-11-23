from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.action_registry import (
    ACTION_SPECS,
    get_action_spec,
    parse_action_kind,
    route_action_request,
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

    def test_route_request_matches_registered_action(self):
        self.assertTrue(
            route_action_request("想看看B站有什么好玩的").startswith("bili:")
        )
        self.assertTrue(route_action_request("想看看你的屏幕").startswith("look:"))
        self.assertTrue(route_action_request("想看看你的手机").startswith("phone_look:"))

    def test_route_request_unknown_returns_empty(self):
        self.assertEqual(route_action_request("想变成一只猫"), "")


if __name__ == "__main__":
    unittest.main()
