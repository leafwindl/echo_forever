from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.infrastructure.context_builder import _trim_history_by_tokens


class HistoryTrimTests(unittest.TestCase):
    def _history(self, count: int, size: int = 2000) -> list[dict]:
        return [
            {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * size}
            for index in range(count)
        ]

    def test_large_budget_keeps_everything(self):
        history = self._history(5)
        self.assertEqual(_trim_history_by_tokens(history, 1_000_000), history)

    def test_small_budget_keeps_latest_only(self):
        history = self._history(5)
        trimmed = _trim_history_by_tokens(history, 10)
        self.assertEqual(len(trimmed), 1)
        self.assertIs(trimmed[0], history[-1])

    def test_zero_budget_does_not_trim(self):
        history = self._history(3)
        self.assertEqual(_trim_history_by_tokens(history, 0), history)

    def test_budget_limits_middle_kept(self):
        history = self._history(20, size=100)
        trimmed = _trim_history_by_tokens(history, 500)
        self.assertGreater(len(trimmed), 1)
        self.assertLess(len(trimmed), 20)
        self.assertIs(trimmed[-1], history[-1])


if __name__ == "__main__":
    unittest.main()
