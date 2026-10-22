"""PostgreSQL operations and atomic enrollment consistency checks."""

import json
import uuid

from db.postgres_connection import get_connection, transaction

from features.devices.domain.speaker_people import SpeakerPeopleError
from features.devices.domain.speaker_vectors import centroid, identify, similarity
from features.devices.infrastructure.device_management import get_user_device


def owned(user_id, device_id):
    if get_user_device(user_id, device_id) is None:
        raise SpeakerPeopleError("not_found", "设备不存在或不属于当前账号")


def lock_owned(cursor, user_id, device_id):
    cursor.execute(
        "SELECT owner_user_id FROM devices WHERE device_id=%s FOR UPDATE",
        (device_id,),
    )
    row = cursor.fetchone()
    if row is None or row["owner_user_id"] != user_id:
        raise SpeakerPeopleError("not_found", "设备不存在或不属于当前账号")


def summary(row):
    return {
        **{k: row[k] for k in ("person_id", "display_name", "status", "sample_count")},
        "hardware_calibrated": row.get("hardware_calibrated", False),
    }


def people(user_id, device_id):
    owned(user_id, device_id)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT p.person_id, p.display_name, p.status, "
            "jsonb_array_length(p.samples) AS sample_count, "
            "c.person_id IS NOT NULL AS hardware_calibrated "
            "FROM speaker_people p LEFT JOIN speaker_device_calibrations c "
            "ON c.person_id=p.person_id WHERE p.owner_user_id=%s AND p.device_id=%s "
            "ORDER BY p.created_at",
            (user_id, device_id),
        )
        return {"items": [summary(row) for row in cursor.fetchall()]}


def create_person(user_id, device_id, display_name):
    person_id = "person_" + uuid.uuid4().hex
    with transaction() as conn, conn.cursor() as cursor:
        # Serialize profile creation per device to enforce a bounded roster.
        lock_owned(cursor, user_id, device_id)
        cursor.execute("SELECT count(*) FROM speaker_people WHERE device_id=%s", (device_id,))
        if cursor.fetchone()["count"] >= 20:
            raise SpeakerPeopleError("conflict", "最多保留 20 位人员，请先删除不用的档案")
        cursor.execute(
            "INSERT INTO speaker_people "
            "(person_id,owner_user_id,device_id,display_name,consented_at) "
            "VALUES (%s,%s,%s,%s,NOW())",
            (person_id, user_id, device_id, display_name.strip()),
        )
    return {
        "person_id": person_id,
        "display_name": display_name.strip(),
        "status": "collecting",
        "sample_count": 0,
    }


def load_person(user_id, device_id, person_id):
    owned(user_id, device_id)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM speaker_people WHERE person_id=%s AND owner_user_id=%s AND device_id=%s",
            (person_id, user_id, device_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise SpeakerPeopleError("not_found", "人员档案不存在")
    return row


def save_sample(user_id, device_id, person_id, vector, model_id, revision, sample_hash):
    with transaction() as conn, conn.cursor() as cursor:
        lock_owned(cursor, user_id, device_id)
        cursor.execute(
            "SELECT * FROM speaker_people WHERE person_id=%s AND owner_user_id=%s "
            "AND device_id=%s FOR UPDATE",
            (person_id, user_id, device_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise SpeakerPeopleError("not_found", "人员档案已删除")
        if row["updated_at"] != revision or row["status"] == "active":
            raise SpeakerPeopleError("conflict", "录入状态已变化，请刷新后重试")
        samples = row["samples"]
        hashes = row["sample_hashes"]
        if sample_hash in hashes:
            raise SpeakerPeopleError("conflict", "请重新录制下一句话，不能重复提交同一段录音")
        if samples and row["model_id"] != model_id:
            raise SpeakerPeopleError("conflict", "模型已更换，请删除此档案后重新录入")
        if samples and similarity(centroid(samples), vector) < 0.65:
            raise SpeakerPeopleError("invalid", "声音与已录入样本不一致，请由同一人重录")
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
                    raise SpeakerPeopleError(
                        "invalid", "与已有成员声纹难以区分，请检查是否重复录入或重新采样"
                    )
            state = "active"
        cursor.execute(
            "UPDATE speaker_people SET samples=%s::jsonb,embedding=%s::jsonb,model_id=%s,"
            "status=%s,sample_hashes=%s::jsonb,updated_at=NOW() WHERE person_id=%s",
            (
                json.dumps(samples),
                json.dumps(centroid(samples)),
                model_id,
                state,
                json.dumps([*hashes, sample_hash]),
                person_id,
            ),
        )
        return {
            "person_id": person_id,
            "display_name": row["display_name"],
            "status": state,
            "sample_count": len(samples),
        }


def save_hardware_calibration(session, verification, model_id):
    candidate = {
        "person_id": session.person_id,
        "display_name": session.name,
        "embedding": centroid(session.samples),
        "model_id": model_id,
        "status": "active",
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
        if (
            identify(verification, model_id, [candidate, *others]).get("person_id")
            != session.person_id
        ):
            raise ValueError("独立验证未通过或与其他成员难以区分，请由本人重读")
        if (
            identify(candidate["embedding"], model_id, [candidate, *others]).get("person_id")
            != session.person_id
        ):
            raise ValueError("与其他成员声纹难以区分，请重新采样")
        cursor.execute(
            "INSERT INTO speaker_device_calibrations "
            "(person_id,device_id,owner_user_id,model_id,samples,embedding) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
            "ON CONFLICT (person_id) DO UPDATE SET model_id=EXCLUDED.model_id,"
            "samples=EXCLUDED.samples,embedding=EXCLUDED.embedding,verified_at=NOW()",
            (
                session.person_id,
                session.device_id,
                session.owner_id,
                model_id,
                json.dumps(session.samples),
                json.dumps(candidate["embedding"]),
            ),
        )


def delete_person(user_id, device_id, person_id):
    owned(user_id, device_id)
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM speaker_people WHERE person_id=%s AND owner_user_id=%s AND device_id=%s",
            (person_id, user_id, device_id),
        )


def delete_calibration(user_id, device_id, person_id):
    with transaction() as conn, conn.cursor() as cursor:
        lock_owned(cursor, user_id, device_id)
        cursor.execute(
            "DELETE FROM speaker_device_calibrations "
            "WHERE person_id=%s AND device_id=%s AND owner_user_id=%s",
            (person_id, device_id, user_id),
        )


def active_profiles(device_id):
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
    return profiles
