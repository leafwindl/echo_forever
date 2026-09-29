"""Explicit-consent, multi-person enrollment. Old prototype profiles are untouched."""
import hashlib
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from features.devices.application.speaker_calibration import SpeakerCalibration
from features.devices.application.speaker_dialogue import SpeakerDialogue

from db.postgres_connection import get_connection, transaction
from features.devices.infrastructure.device_management import get_user_device
from features.devices.infrastructure.neural_speaker import (
    SpeakerUnavailable, centroid, extract, identify, similarity,
)
from shared.interface.dependencies import CurrentUser, get_current_user

router = APIRouter(prefix="/devices", tags=["speaker-enrollment"])
logger = logging.getLogger(__name__)
User = Annotated[CurrentUser, Depends(get_current_user)]


class ApprovalRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    approved: bool


class PersonRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)
    consent: bool


class CalibrationRequest(BaseModel):
    consent: bool


def owned(user_id, device_id):
    if get_user_device(user_id, device_id) is None:
        raise HTTPException(404, "设备不存在或不属于当前账号")


def lock_owned(cursor, user_id, device_id):
    cursor.execute(
        "SELECT owner_user_id FROM devices WHERE device_id=%s FOR UPDATE", (device_id,),
    )
    row = cursor.fetchone()
    if row is None or row["owner_user_id"] != user_id:
        raise HTTPException(404, "设备不存在或不属于当前账号")


def summary(row):
    return {
        **{k: row[k] for k in ("person_id", "display_name", "status", "sample_count")},
        "hardware_calibrated": row.get("hardware_calibrated", False),
    }


@router.get("/{device_id}/speakers")
def people(device_id: str, current_user: User):
    owned(current_user.user_id, device_id)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT p.person_id, p.display_name, p.status, "
            "jsonb_array_length(p.samples) AS sample_count, "
            "c.person_id IS NOT NULL AS hardware_calibrated "
            "FROM speaker_people p LEFT JOIN speaker_device_calibrations c "
            "ON c.person_id=p.person_id WHERE p.owner_user_id=%s AND p.device_id=%s "
            "ORDER BY p.created_at",
            (current_user.user_id, device_id),
        )
        return {"items": [summary(row) for row in cursor.fetchall()]}


@router.post("/{device_id}/speakers", status_code=201)
def create_person(device_id: str, body: PersonRequest, current_user: User):
    owned(current_user.user_id, device_id)
    if not body.consent or not body.display_name.strip():
        raise HTTPException(422, "需本人同意录入并填写称呼")
    person_id = "person_" + uuid.uuid4().hex
    with transaction() as conn, conn.cursor() as cursor:
        # Serialize profile creation per device to enforce a bounded roster.
        lock_owned(cursor, current_user.user_id, device_id)
        cursor.execute("SELECT count(*) FROM speaker_people WHERE device_id=%s", (device_id,))
        if cursor.fetchone()["count"] >= 20:
            raise HTTPException(409, "最多保留 20 位人员，请先删除不用的档案")
        cursor.execute(
            "INSERT INTO speaker_people (person_id,owner_user_id,device_id,display_name,consented_at) "
            "VALUES (%s,%s,%s,%s,NOW())",
            (person_id, current_user.user_id, device_id, body.display_name.strip()),
        )
    return {"person_id": person_id, "display_name": body.display_name.strip(),
            "status": "collecting", "sample_count": 0}


def load_person(user_id, device_id, person_id):
    owned(user_id, device_id)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM speaker_people WHERE person_id=%s AND owner_user_id=%s AND device_id=%s",
            (person_id, user_id, device_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "人员档案不存在")
    return row


@router.post("/{device_id}/speakers/{person_id}/samples")
async def add_sample(
    device_id: str, person_id: str, current_user: User,
    audio: Annotated[UploadFile, File()],
):
    data = await audio.read(384001)
    return await enroll_audio(current_user.user_id, device_id, person_id, data)


async def enroll_audio(user_id, device_id, person_id, data):
    person = await run_in_threadpool(load_person, user_id, device_id, person_id)
    if person["status"] == "active":
        raise HTTPException(409, "档案已完成，请勿重复录入")
    if len(data) > 384000:
        raise HTTPException(413, "录音最长为 12 秒")
    try:
        vector, model_id = await run_in_threadpool(extract, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except SpeakerUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return await run_in_threadpool(
        save_sample, user_id, device_id, person_id, vector, model_id,
        person["updated_at"], hashlib.sha256(data).hexdigest(),
    )


def save_sample(user_id, device_id, person_id, vector, model_id, revision, sample_hash):
    with transaction() as conn, conn.cursor() as cursor:
        lock_owned(cursor, user_id, device_id)
        cursor.execute(
            "SELECT * FROM speaker_people WHERE person_id=%s AND owner_user_id=%s "
            "AND device_id=%s FOR UPDATE", (person_id, user_id, device_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(404, "人员档案已删除")
        if row["updated_at"] != revision or row["status"] == "active":
            raise HTTPException(409, "录入状态已变化，请刷新后重试")
        samples = row["samples"]
        hashes = row["sample_hashes"]
        if sample_hash in hashes:
            raise HTTPException(409, "请重新录制下一句话，不能重复提交同一段录音")
        if samples and row["model_id"] != model_id:
            raise HTTPException(409, "模型已更换，请删除此档案后重新录入")
        if samples and similarity(centroid(samples), vector) < 0.65:
            raise HTTPException(422, "声音与已录入样本不一致，请由同一人重录")
        state = "collecting"
        if len(samples) < 3:
            samples = [*samples, vector]
            state = "verifying" if len(samples) == 3 else "collecting"
        else:
            # The fourth utterance is held out; it never changes the enrollment centroid.
            cursor.execute(
                "SELECT * FROM speaker_people WHERE device_id=%s AND owner_user_id=%s "
                "AND person_id<>%s AND status='active' AND model_id=%s",
                (device_id, user_id, person_id, model_id),
            )
            others = cursor.fetchall()
            candidate = {**row, "embedding": centroid(samples), "status": "active"}
            for check_vector in (vector, candidate["embedding"]):
                result = identify(check_vector, model_id, [candidate, *others])
                if result.get("person_id") != person_id:
                    raise HTTPException(422, "与已有成员声纹难以区分，请检查是否重复录入或重新采样")
            state = "active"
        cursor.execute(
            "UPDATE speaker_people SET samples=%s::jsonb,embedding=%s::jsonb,model_id=%s,"
            "status=%s,sample_hashes=%s::jsonb,updated_at=NOW() WHERE person_id=%s",
            (json.dumps(samples), json.dumps(centroid(samples)), model_id, state,
             json.dumps([*hashes, sample_hash]), person_id),
        )
        return {"person_id": person_id, "display_name": row["display_name"],
                "status": state, "sample_count": len(samples)}


@router.delete("/{device_id}/speakers/{person_id}", status_code=204)
def delete_person(device_id: str, person_id: str, current_user: User):
    owned(current_user.user_id, device_id)
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM speaker_people WHERE person_id=%s AND owner_user_id=%s AND device_id=%s",
            (person_id, current_user.user_id, device_id),
        )
    hardware_calibration.cancel(current_user.user_id, device_id)


def save_hardware_calibration(session, verification, model_id):
    candidate = {
        "person_id": session.person_id, "display_name": session.name,
        "embedding": centroid(session.samples), "model_id": model_id, "status": "active",
    }
    with transaction() as conn, conn.cursor() as cursor:
        lock_owned(cursor, session.owner_id, session.device_id)
        cursor.execute(
            "SELECT status, model_id FROM speaker_people WHERE person_id=%s "
            "AND owner_user_id=%s AND device_id=%s FOR UPDATE",
            (session.person_id, session.owner_id, session.device_id),
        )
        person = cursor.fetchone()
        if not person or person["status"] != "active" or person["model_id"] != model_id:
            raise ValueError("手机声纹档案已变化，请重新开始")
        cursor.execute(
            "SELECT p.person_id,p.display_name,p.model_id,p.status,"
            "COALESCE(c.embedding,p.embedding) AS embedding FROM speaker_people p "
            "LEFT JOIN speaker_device_calibrations c ON c.person_id=p.person_id "
            "WHERE p.device_id=%s AND p.owner_user_id=%s AND p.status='active' AND p.person_id<>%s",
            (session.device_id, session.owner_id, session.person_id),
        )
        others = cursor.fetchall()
        if identify(verification, model_id, [candidate, *others]).get("person_id") != session.person_id:
            raise ValueError("独立验证未通过或与其他成员难以区分，请由本人重读")
        if identify(candidate["embedding"], model_id, [candidate, *others]).get("person_id") != session.person_id:
            raise ValueError("与其他成员声纹难以区分，请重新采样")
        cursor.execute(
            "INSERT INTO speaker_device_calibrations "
            "(person_id,device_id,owner_user_id,model_id,samples,embedding) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
            "ON CONFLICT (person_id) DO UPDATE SET model_id=EXCLUDED.model_id,"
            "samples=EXCLUDED.samples,embedding=EXCLUDED.embedding,verified_at=NOW()",
            (session.person_id, session.device_id, session.owner_id, model_id,
             json.dumps(session.samples), json.dumps(candidate["embedding"])),
        )


hardware_calibration = SpeakerCalibration(save_hardware_calibration)


@router.post("/{device_id}/speakers/{person_id}/calibration")
def start_calibration(device_id: str, person_id: str, body: CalibrationRequest, current_user: User):
    if not body.consent:
        raise HTTPException(422, "请先获得录入者本人同意")
    person = load_person(current_user.user_id, device_id, person_id)
    if person["status"] != "active":
        raise HTTPException(409, "请先完成 App 声纹录入")
    from features.devices.interface.router import _active_device_sessions
    if device_id.strip().lower() not in _active_device_sessions:
        raise HTTPException(409, "Echo 当前不在线")
    try:
        return hardware_calibration.start(
            current_user.user_id, device_id.strip().lower(), person_id, person["display_name"],
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{device_id}/speaker-calibration")
def calibration_status(device_id: str, current_user: User):
    owned(current_user.user_id, device_id)
    return {"session": hardware_calibration.pending(current_user.user_id, device_id.strip().lower())}


@router.delete("/{device_id}/speaker-calibration", status_code=204)
def cancel_calibration(device_id: str, current_user: User):
    owned(current_user.user_id, device_id)
    hardware_calibration.cancel(current_user.user_id, device_id.strip().lower())


@router.delete("/{device_id}/speakers/{person_id}/calibration", status_code=204)
def delete_calibration(device_id: str, person_id: str, current_user: User):
    with transaction() as conn, conn.cursor() as cursor:
        lock_owned(cursor, current_user.user_id, device_id)
        cursor.execute(
            "DELETE FROM speaker_device_calibrations WHERE person_id=%s AND device_id=%s AND owner_user_id=%s",
            (person_id, device_id, current_user.user_id),
        )
    hardware_calibration.cancel(current_user.user_id, device_id.strip().lower())


def recognize(device_id, audio):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT p.*, COALESCE(c.embedding,p.embedding) AS embedding, "
            "COALESCE(c.model_id,p.model_id) AS model_id "
            "FROM speaker_people p JOIN devices d ON d.device_id=p.device_id "
            "AND d.owner_user_id=p.owner_user_id "
            "LEFT JOIN speaker_device_calibrations c ON c.person_id=p.person_id "
            "WHERE p.device_id=%s AND p.status='active'",
            (device_id,),
        )
        profiles = cursor.fetchall()
    if not profiles:
        logger.warning(
            "Device speaker verification skipped device_id=%s reason=no_active_profiles",
            device_id,
        )
        return {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
    try:
        vector, model_id = extract(audio)
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
        (profile for profile in profiles
         if profile.get("person_id") == result.get("person_id")),
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


async def create_voice_person(user_id, device_id, name):
    result = await run_in_threadpool(
        create_person, device_id, PersonRequest(display_name=name, consent=True),
        CurrentUser(user_id=user_id),
    )
    return result["person_id"]


voice_enrollment = SpeakerDialogue(create_voice_person, enroll_audio)


@router.get("/{device_id}/speaker-enrollment-request")
async def enrollment_request(device_id: str, current_user: User):
    await run_in_threadpool(owned, current_user.user_id, device_id)
    return {"request": voice_enrollment.pending(current_user.user_id, device_id)}


@router.post("/{device_id}/speaker-enrollment-request")
async def approve_enrollment(device_id: str, body: ApprovalRequest, current_user: User):
    await run_in_threadpool(owned, current_user.user_id, device_id)
    try:
        if body.approved:
            voice_enrollment.approve(current_user.user_id, device_id, body.session_id)
        else:
            voice_enrollment.cancel(current_user.user_id, device_id, body.session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"approved": body.approved}
