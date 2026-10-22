"""Wire the speaker workflows used by HTTP and device WebSocket sessions."""

import asyncio

from features.devices.application.speaker_calibration import SpeakerCalibration
from features.devices.application.speaker_dialogue import SpeakerDialogue
from features.devices.application.speaker_people import SpeakerPeopleService
from features.devices.infrastructure import speaker_people_repository as repository
from features.devices.infrastructure.device_sessions import active_device_sessions
from features.devices.infrastructure.neural_speaker import extract

hardware_calibration = SpeakerCalibration(repository.save_hardware_calibration)
people_service = SpeakerPeopleService(
    repository, extract, hardware_calibration, lambda device_id: device_id in active_device_sessions
)


async def create_voice_person(user_id, device_id, name):
    result = await asyncio.to_thread(
        people_service.create_person, user_id, device_id, name, consent=True
    )
    return result["person_id"]


voice_enrollment = SpeakerDialogue(create_voice_person, people_service.enroll_audio)
recognize = people_service.recognize
