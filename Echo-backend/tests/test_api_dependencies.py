import unittest
from pathlib import Path
import sys

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.interface.dependencies import resolve_current_user


class ResolveCurrentUserTests(unittest.TestCase):
    def test_uses_body_user_id_for_legacy_clients(self):
        user = resolve_current_user(body_user_id="  user_a  ")

        self.assertEqual(user.user_id, "user_a")

    def test_accepts_matching_header_and_body_user_id(self):
        user = resolve_current_user(header_user_id="user_a", body_user_id="user_a")

        self.assertEqual(user.user_id, "user_a")

    def test_rejects_missing_user_id(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user()

        self.assertEqual(error.exception.status_code, 400)

    def test_rejects_conflicting_user_identity(self):
        with self.assertRaises(HTTPException) as error:
            resolve_current_user(header_user_id="user_a", body_user_id="user_b")

        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
