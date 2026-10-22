"""Contracts for the implemented multi-person speaker enrollment workflow."""

from typing import Protocol


class SpeakerPeopleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SpeakerPeopleRepository(Protocol):
    def owned(self, user_id: str, device_id: str) -> None: ...

    def people(self, user_id: str, device_id: str) -> dict: ...

    def create_person(self, user_id: str, device_id: str, display_name: str) -> dict: ...

    def load_person(self, user_id: str, device_id: str, person_id: str) -> dict: ...

    def save_sample(
        self, user_id, device_id, person_id, vector, model_id, revision, sample_hash
    ) -> dict: ...

    def delete_person(self, user_id: str, device_id: str, person_id: str) -> None: ...

    def delete_calibration(self, user_id: str, device_id: str, person_id: str) -> None: ...

    def active_profiles(self, device_id: str) -> list[dict]: ...
