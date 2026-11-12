import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.relationship.domain.entities import RelationshipState
from features.relationship.interface.router import relationship_get, relationship_reset
from shared.config import settings
from shared.interface.dependencies import CurrentUser


class RelationshipInterfaceTests(unittest.TestCase):
    # 该用例原本只 patch 了 state 取数，pending proposal 仍会连接真实数据库。
    # 无 DATABASE_URL 时显式跳过，避免把环境缺失当成代码失败。
    @unittest.skipUnless(settings.database_url, "requires DATABASE_URL")
    @patch(
        "features.relationship.interface.router.get_pending_relationship_proposal",
        return_value=None,
    )
    @patch("features.relationship.interface.router.get_relationship_state")
    def test_get_uses_authenticated_user_and_does_not_expose_score(
        self, mock_get, mock_pending
    ):
        mock_get.return_value = RelationshipState(
            user_id="user-token",
            stage="familiar",
            score=37,
            interaction_turns=18,
            active_days=4,
        )

        response = relationship_get(CurrentUser(user_id="user-token"))

        mock_get.assert_called_once_with("user-token")
        mock_pending.assert_called_once_with("user-token")
        self.assertEqual("熟悉", response.stage_label)
        self.assertNotIn("score", response.model_dump())

    @patch("features.relationship.interface.router.reset_relationship_state")
    def test_reset_only_targets_authenticated_user(self, mock_reset):
        mock_reset.return_value = RelationshipState(user_id="user-token")

        response = relationship_reset(CurrentUser(user_id="user-token"))

        mock_reset.assert_called_once_with("user-token")
        self.assertEqual("new", response.stage)


if __name__ == "__main__":
    unittest.main()

