"""Use-case guards must survive moving enrollment out of HTTP handlers."""

import hashlib
import unittest
from unittest.mock import Mock

from features.devices.application.speaker_people import SpeakerPeopleService
from features.devices.domain.speaker_people import SpeakerPeopleError, SpeakerPeopleRepository
from features.devices.domain.speaker_vectors import SpeakerUnavailable


class SpeakerPeopleUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = Mock(spec=SpeakerPeopleRepository)
        self.repository.load_person.return_value = {
            "status": "collecting",
            "updated_at": "revision-1",
            "display_name": "Alice",
        }
        self.extract = Mock(return_value=([1.0, 0.0], "campp-zh:test"))
        self.calibration = Mock()
        self.is_online = Mock(return_value=True)
        self.service = SpeakerPeopleService(
            self.repository, self.extract, self.calibration, self.is_online
        )

    def test_consent_is_required_before_creating_a_profile(self):
        with self.assertRaises(SpeakerPeopleError) as error:
            self.service.create_person("owner", "device", "Alice", consent=False)
        self.assertEqual(error.exception.code, "invalid")
        self.repository.create_person.assert_not_called()

    def test_calibration_requires_an_active_profile_and_online_device(self):
        with self.assertRaises(SpeakerPeopleError):
            self.service.start_calibration("owner", "device", "person", consent=True)
        self.repository.load_person.return_value["status"] = "active"
        self.is_online.return_value = False
        with self.assertRaises(SpeakerPeopleError) as error:
            self.service.start_calibration("owner", "device", "person", consent=True)
        self.assertEqual(error.exception.code, "conflict")
        self.calibration.start.assert_not_called()

    def test_foreign_owner_cannot_read_pending_calibration(self):
        self.repository.owned.side_effect = SpeakerPeopleError("not_found", "Not owned")
        with self.assertRaises(SpeakerPeopleError):
            self.service.calibration_status("other", "device")
        self.calibration.pending.assert_not_called()

    async def test_unavailable_extractor_never_saves_a_sample(self):
        self.extract.side_effect = SpeakerUnavailable("Offline")
        with self.assertRaises(SpeakerPeopleError) as error:
            await self.service.enroll_audio("owner", "device", "person", b"audio")
        self.assertEqual(error.exception.code, "unavailable")
        self.repository.save_sample.assert_not_called()

    async def test_raw_audio_is_not_passed_to_persistence(self):
        await self.service.enroll_audio("owner", "device", "person", b"audio")
        self.repository.save_sample.assert_called_once_with(
            "owner",
            "device",
            "person",
            [1.0, 0.0],
            "campp-zh:test",
            "revision-1",
            hashlib.sha256(b"audio").hexdigest(),
        )

    async def test_oversized_audio_never_reaches_the_extractor(self):
        with self.assertRaises(SpeakerPeopleError) as error:
            await self.service.enroll_audio("owner", "device", "person", b"0" * 384001)
        self.assertEqual(error.exception.code, "too_large")
        self.extract.assert_not_called()
        self.repository.save_sample.assert_not_called()
