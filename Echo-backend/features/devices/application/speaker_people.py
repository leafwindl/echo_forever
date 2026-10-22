"""Use cases for consent, enrollment and speaker attribution; no HTTP or SQL."""

import asyncio
import hashlib
import logging

from features.devices.domain.speaker_people import SpeakerPeopleError, SpeakerPeopleRepository
from features.devices.domain.speaker_vectors import SpeakerUnavailable, identify

logger = logging.getLogger(__name__)


class SpeakerPeopleService:
    def __init__(self, repository: SpeakerPeopleRepository, extract, calibration, is_online):
        self.repository = repository
        self.extract = extract
        self.calibration = calibration
        self.is_online = is_online

    def owned(self, user_id, device_id):
        self.repository.owned(user_id, device_id)

    def people(self, user_id, device_id):
        return self.repository.people(user_id, device_id)

    def create_person(self, user_id, device_id, display_name, consent):
        self.repository.owned(user_id, device_id)
        if not consent or not display_name.strip():
            raise SpeakerPeopleError("invalid", "需本人同意录入并填写称呼")
        return self.repository.create_person(user_id, device_id, display_name.strip())

    def delete_person(self, user_id, device_id, person_id):
        self.repository.delete_person(user_id, device_id, person_id)
        self.calibration.cancel(user_id, device_id)

    def start_calibration(self, user_id, device_id, person_id, consent):
        if not consent:
            raise SpeakerPeopleError("invalid", "请先获得录入者本人同意")
        person = self.repository.load_person(user_id, device_id, person_id)
        if person["status"] != "active":
            raise SpeakerPeopleError("conflict", "请先完成 App 声纹录入")
        device_key = device_id.strip().lower()
        if not self.is_online(device_key):
            raise SpeakerPeopleError("conflict", "Echo 当前不在线")
        try:
            return self.calibration.start(user_id, device_key, person_id, person["display_name"])
        except ValueError as error:
            raise SpeakerPeopleError("conflict", str(error)) from error

    def calibration_status(self, user_id, device_id):
        self.repository.owned(user_id, device_id)
        return {"session": self.calibration.pending(user_id, device_id.strip().lower())}

    def cancel_calibration(self, user_id, device_id):
        self.repository.owned(user_id, device_id)
        self.calibration.cancel(user_id, device_id.strip().lower())

    def delete_calibration(self, user_id, device_id, person_id):
        self.repository.delete_calibration(user_id, device_id, person_id)
        self.calibration.cancel(user_id, device_id.strip().lower())

    async def enroll_audio(self, user_id, device_id, person_id, data):
        person = await asyncio.to_thread(self.repository.load_person, user_id, device_id, person_id)
        if person["status"] == "active":
            raise SpeakerPeopleError("conflict", "档案已完成，请勿重复录入")
        if len(data) > 384000:
            raise SpeakerPeopleError("too_large", "录音最长为 12 秒")
        try:
            vector, model_id = await asyncio.to_thread(self.extract, data)
        except ValueError as exc:
            raise SpeakerPeopleError("invalid", str(exc)) from exc
        except SpeakerUnavailable as exc:
            raise SpeakerPeopleError("unavailable", str(exc)) from exc
        return await asyncio.to_thread(
            self.repository.save_sample,
            user_id,
            device_id,
            person_id,
            vector,
            model_id,
            person["updated_at"],
            hashlib.sha256(data).hexdigest(),
        )

    def recognize(self, device_id, audio):
        profiles = self.repository.active_profiles(device_id)
        if not profiles:
            logger.warning(
                "Device speaker verification skipped device_id=%s reason=no_active_profiles",
                device_id,
            )
            return {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
        try:
            vector, model_id = self.extract(audio)
        except ValueError as exc:
            logger.info(
                "Device speaker verification rejected device_id=%s reason=invalid_audio detail=%s",
                device_id,
                str(exc),
            )
            return {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
        except SpeakerUnavailable as exc:
            logger.warning(
                "Device speaker verification unavailable device_id=%s detail=%s",
                device_id,
                str(exc),
            )
            return {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
        result = identify(vector, model_id, profiles, diagnostics=True)
        logger.info(
            "Device speaker verification device_id=%s status=%s model_id=%s "
            "candidate_count=%s best_similarity=%s",
            device_id,
            result.get("status"),
            model_id,
            result.get("candidate_count"),
            result.get("best_similarity"),
        )
        result.pop("candidate_count", None)
        result.pop("best_similarity", None)
        if result.get("status") != "matched":
            return {**result, "speaker_role": "unknown", "confidence": 0.0}
        matched_profile = next(
            (
                profile
                for profile in profiles
                if profile.get("person_id") == result.get("person_id")
            ),
            None,
        )
        if matched_profile is None:
            return {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
        # A recognized person is known for attribution only. It never grants owner
        # authorization or owner-only memory access.
        return {
            **result,
            "speaker_profile_id": matched_profile["person_id"],
            "speaker_role": "known",
            "confidence": float(result["similarity"]),
        }
