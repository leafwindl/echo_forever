"""HTTP endpoints for implemented speaker enrollment and calibration use cases."""

import functools
import inspect
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from shared.interface.dependencies import CurrentUser, get_current_user
from starlette.concurrency import run_in_threadpool

from features.devices.domain.speaker_people import SpeakerPeopleError
from features.devices.infrastructure.speaker_people_container import (
    people_service,
    voice_enrollment,
)

router = APIRouter(prefix="/devices", tags=["speaker-enrollment"])
User = Annotated[CurrentUser, Depends(get_current_user)]


def map_speaker_errors(function):
    def translate(error):
        codes = {
            "not_found": 404,
            "conflict": 409,
            "invalid": 422,
            "too_large": 413,
            "unavailable": 503,
        }
        return HTTPException(codes[error.code], str(error))

    if inspect.iscoroutinefunction(function):

        @functools.wraps(function)
        async def async_handler(*args, **kwargs):
            try:
                return await function(*args, **kwargs)
            except SpeakerPeopleError as error:
                raise translate(error) from error

        return async_handler

    @functools.wraps(function)
    def handler(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SpeakerPeopleError as error:
            raise translate(error) from error

    return handler


class ApprovalRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    approved: bool


class PersonRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)
    consent: bool


class CalibrationRequest(BaseModel):
    consent: bool


@router.get("/{device_id}/speakers")
@map_speaker_errors
def people(device_id: str, current_user: User):
    return people_service.people(current_user.user_id, device_id)


@router.post("/{device_id}/speakers", status_code=201)
@map_speaker_errors
def create_person(device_id: str, body: PersonRequest, current_user: User):
    return people_service.create_person(
        current_user.user_id, device_id, body.display_name, body.consent
    )


@router.post("/{device_id}/speakers/{person_id}/samples")
@map_speaker_errors
async def add_sample(
    device_id: str,
    person_id: str,
    current_user: User,
    audio: Annotated[UploadFile, File()],
):
    data = await audio.read(384001)
    return await people_service.enroll_audio(current_user.user_id, device_id, person_id, data)


@router.delete("/{device_id}/speakers/{person_id}", status_code=204)
@map_speaker_errors
def delete_person(device_id: str, person_id: str, current_user: User):
    people_service.delete_person(current_user.user_id, device_id, person_id)


@router.post("/{device_id}/speakers/{person_id}/calibration")
@map_speaker_errors
def start_calibration(device_id: str, person_id: str, body: CalibrationRequest, current_user: User):
    return people_service.start_calibration(
        current_user.user_id, device_id, person_id, body.consent
    )


@router.get("/{device_id}/speaker-calibration")
@map_speaker_errors
def calibration_status(device_id: str, current_user: User):
    return people_service.calibration_status(current_user.user_id, device_id)


@router.delete("/{device_id}/speaker-calibration", status_code=204)
@map_speaker_errors
def cancel_calibration(device_id: str, current_user: User):
    people_service.cancel_calibration(current_user.user_id, device_id)


@router.delete("/{device_id}/speakers/{person_id}/calibration", status_code=204)
@map_speaker_errors
def delete_calibration(device_id: str, person_id: str, current_user: User):
    people_service.delete_calibration(current_user.user_id, device_id, person_id)


@router.get("/{device_id}/speaker-enrollment-request")
@map_speaker_errors
async def enrollment_request(device_id: str, current_user: User):
    await run_in_threadpool(people_service.owned, current_user.user_id, device_id)
    return {"request": voice_enrollment.pending(current_user.user_id, device_id)}


@router.post("/{device_id}/speaker-enrollment-request")
@map_speaker_errors
async def approve_enrollment(device_id: str, body: ApprovalRequest, current_user: User):
    await run_in_threadpool(people_service.owned, current_user.user_id, device_id)
    try:
        if body.approved:
            voice_enrollment.approve(current_user.user_id, device_id, body.session_id)
        else:
            voice_enrollment.cancel(current_user.user_id, device_id, body.session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"approved": body.approved}
