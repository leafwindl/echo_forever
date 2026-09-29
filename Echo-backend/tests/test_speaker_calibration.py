import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.devices.application.speaker_calibration import SpeakerCalibration
from features.devices.infrastructure.neural_speaker import SpeakerUnavailable


class SpeakerCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.saved = []
        self.calibration = SpeakerCalibration(
            lambda session, verification, model: self.saved.append(
                (list(session.samples), verification, model)
            ),
            clock=lambda: self.now,
        )
        self.calibration.start("owner", "device", "person", "叶子")

    def consume(self, index, vector=(1., 0.), model="campp-zh:test"):
        return self.calibration.consume(
            "owner", "device", bytes([index]), lambda audio: (list(vector), model),
        )

    def test_three_samples_and_independent_verification(self):
        for index in range(1, 4):
            self.assertIn(f"第{index}段", self.consume(index))
        self.assertEqual(self.calibration.pending("owner", "device")["state"], "verifying")
        self.assertEqual(self.saved, [])
        self.assertIn("独立验证", self.consume(4))
        self.assertEqual(len(self.saved[0][0]), 3)
        self.assertEqual(self.saved[0][1], [1., 0.])
        self.assertIsNone(self.calibration.pending("owner", "device"))

    def test_rejected_audio_and_verification_can_retry(self):
        self.consume(1)
        self.assertIn("未通过", self.consume(1))
        self.assertIn("未通过", self.consume(2, (0., 1.)))
        self.assertIn("未通过", self.consume(2, model="campp-zh:new"))
        self.assertEqual(self.calibration.pending("owner", "device")["sample_count"], 1)
        self.consume(2)
        self.consume(3)
        self.assertIn("未通过", self.consume(4, (0., 1.)))
        self.assertEqual(self.calibration.pending("owner", "device")["sample_count"], 3)
        self.assertEqual(self.saved, [])
        self.assertIn("独立验证", self.consume(5))

    def test_service_or_database_failure_does_not_leave_busy_session(self):
        self.calibration.consume(
            "owner", "device", b"first",
            lambda audio: (_ for _ in ()).throw(SpeakerUnavailable("模型不可用")),
        )
        self.assertIn("模型不可用", self.calibration.pending("owner", "device")["error"])
        for index in range(1, 4):
            self.consume(index)
        self.calibration.save = lambda *args: (_ for _ in ()).throw(RuntimeError("db"))
        self.assertIn("未保存", self.consume(4))
        session = self.calibration.pending("owner", "device")
        self.assertEqual(session["sample_count"], 3)
        self.assertFalse(self.calibration.sessions["device"].busy)
        self.calibration.save = lambda *args: self.saved.append(args)
        self.assertIn("独立验证", self.consume(4))

    def test_cancel_expiry_and_account_boundary(self):
        self.assertIsNone(self.calibration.pending("other", "device"))
        self.assertIsNone(self.calibration.consume("other", "device", b"x", lambda _: None))
        self.calibration.cancel("other", "device")
        self.assertTrue(self.calibration.active("owner", "device"))
        self.calibration.cancel("owner", "device", "wrong-session")
        self.assertTrue(self.calibration.active("owner", "device"))
        self.now += 601
        self.assertFalse(self.calibration.active("owner", "device"))
        self.assertIsNone(self.consume(1))
        self.calibration.start("owner", "device", "person", "叶子")
        self.calibration.cancel("owner", "device")
        self.assertIsNone(self.calibration.pending("owner", "device"))


if __name__ == "__main__":
    unittest.main()
