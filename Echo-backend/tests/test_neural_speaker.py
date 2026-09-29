import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from features.devices.infrastructure.neural_speaker import (
    SpeakerUnavailable, centroid, extract, identify, similarity,
)
from features.devices.interface import speaker_router as routes


class NeuralSpeakerTests(unittest.TestCase):
    def profile(self, vector, model="campp-zh:test", state="active", name="A"):
        return dict(person_id=name, display_name=name, model_id=model,
                    embedding=vector, status=state)

    def test_no_fallback_without_model_service(self):
        with patch.dict(os.environ, {"ECHO_SPEAKER_SERVICE_URL": ""}):
            with self.assertRaises(SpeakerUnavailable):
                extract(b"\x00" * 128000)

    def test_rejects_unknown_and_model_mismatch(self):
        self.assertEqual(identify([1, 0], "campp-zh:test", [self.profile([0, 1])])["status"], "unknown")
        self.assertEqual(identify([1, 0], "campp-zh:new", [self.profile([1, 0])])["status"], "unknown")

    def test_ambiguous_candidates_are_not_forced_to_match(self):
        result = identify([1, 0], "campp-zh:test", [
            self.profile([1, 0]), self.profile([0.99, 0.01], name="B"),
        ])
        self.assertEqual(result, {"status": "uncertain"})

    def test_diagnostics_report_similarity_without_identifying_low_match(self):
        result = identify([1, 0], "campp-zh:test", [
            self.profile([0.6, 0.8]),
        ], diagnostics=True)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["candidate_count"], 1)
        self.assertAlmostEqual(result["best_similarity"], 0.6)
        self.assertNotIn("person_id", result)

    def test_collecting_profile_is_not_identified(self):
        result = identify([1, 0], "campp-zh:test", [self.profile([1, 0], state="collecting")])
        self.assertEqual(result, {"status": "unknown"})

    def test_matching_does_not_grant_owner_role(self):
        result = identify([1, 0], "campp-zh:test", [self.profile([1, 0])])
        self.assertEqual(result["display_name"], "A")
        self.assertNotIn("speaker_role", result)

    def test_recognize_preserves_matched_person_without_owner_role(self):
        profile = self.profile([1, 0], name="person_a")
        with patch.object(routes, "get_connection") as get_connection, \
                patch.object(routes, "extract", return_value=([1, 0], "campp-zh:test")), \
                patch.object(routes, "identify", return_value={
                    "status": "matched",
                    "person_id": "person_a",
                    "display_name": "A",
                    "similarity": 0.91,
                }):
            cursor = get_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [profile]
            result = routes.recognize("device", b"audio")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["speaker_profile_id"], "person_a")
        self.assertEqual(result["speaker_role"], "known")
        self.assertAlmostEqual(result["confidence"], 0.91)

    def test_centroid_and_similarity_normalize(self):
        self.assertAlmostEqual(similarity([3, 0], [2, 0]), 1)
        self.assertEqual(centroid([[1, 0], [1, 0]]), [1, 0])
        self.assertEqual(similarity([1, 0], [1]), -1)

    def test_consent_required_before_profile_created(self):
        with patch.object(routes, "owned"):
            with self.assertRaises(HTTPException) as error:
                routes.create_person("device", routes.PersonRequest(display_name="A", consent=False),
                                     routes.CurrentUser(user_id="owner"))
        self.assertEqual(error.exception.status_code, 422)

    def test_cross_account_access_is_denied(self):
        with patch.object(routes, "get_user_device", return_value=None):
            with self.assertRaises(HTTPException) as error:
                routes.load_person("other", "device", "person")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
