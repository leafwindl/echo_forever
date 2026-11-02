from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.presence.domain.entities import PresenceState, PresenceThought
from features.presence.interface.router import get_my_presence
from shared.interface.dependencies import CurrentUser


class PresenceInterfaceTests(unittest.TestCase):
    def test_returns_state_thoughts_and_budget_for_authenticated_user(self):
        now = datetime.now(UTC)
        state = PresenceState(
            user_id="user-1",
            status="idle",
            last_thought_at=now,
            thoughts_used=2,
        )
        thought = PresenceThought(
            thought_id="thought_1",
            user_id="user-1",
            text="今天她好像有点累",
            salience=0.6,
            shareable=False,
            created_at=now,
        )
        with (
            patch("features.presence.interface.router.get_presence_state", return_value=state),
            patch(
                "features.presence.interface.router.list_presence_thoughts",
                return_value=[thought],
            ),
        ):
            response = get_my_presence(CurrentUser(user_id="user-1"))
        self.assertEqual(response.status, "idle")
        self.assertEqual(response.thoughts_used, 2)
        self.assertEqual(response.thoughts[0].text, "今天她好像有点累")


if __name__ == "__main__":
    unittest.main()
