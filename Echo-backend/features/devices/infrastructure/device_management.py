from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime

from db.postgres_connection import get_connection, transaction


def normalize_device_id(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_client_id(value: str) -> str:
    return str(value or "").strip().lower()


def hash_credential(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_device_credential() -> tuple[str, str]:
    raw = f"edc_{secrets.token_urlsafe(32)}"
    return raw, hash_credential(raw)


def _device_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("created_at", "updated_at", "last_seen_at", "bound_at"):
        value = result.get(key)
        if isinstance(value, datetime):
            result[key] = value.astimezone(UTC).isoformat()
    return result


def create_pairing(*, device_id: str, client_id: str, firmware_version: str = "") -> dict:
    clean_device_id = normalize_device_id(device_id)
    clean_client_id = normalize_client_id(client_id)
    if not clean_device_id:
        raise ValueError("device_id is required")
    code = f"{secrets.randbelow(1_000_000):06d}"
    pairing_id = f"pair_{uuid.uuid4().hex}"
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO devices (device_id, client_id, firmware_version, status, last_seen_at)
            VALUES (%s, %s, %s, 'unclaimed', NOW())
            ON CONFLICT (device_id) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                firmware_version = COALESCE(NULLIF(EXCLUDED.firmware_version, ''), devices.firmware_version),
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            (clean_device_id, clean_client_id, firmware_version.strip()),
        )
        cursor.execute(
            """
            INSERT INTO device_pairings (pairing_id, device_id, client_id, code_hash, expires_at)
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '5 minutes')
            """,
            (pairing_id, clean_device_id, clean_client_id, hash_credential(code)),
        )
    return {"pairing_id": pairing_id, "code": code, "expires_in": 300}


def claim_pairing(*, user_id: str, pairing_id: str, code: str) -> dict:
    clean_code = str(code or "").strip()
    with transaction() as conn, conn.cursor() as cursor:
        if pairing_id.strip():
            cursor.execute(
                """
                SELECT pairing_id, device_id, client_id, code_hash, attempts, expires_at, claimed_at
                FROM device_pairings
                WHERE pairing_id = %s
                FOR UPDATE
                """,
                (pairing_id.strip(),),
            )
        else:
            cursor.execute(
                """
                SELECT pairing_id, device_id, client_id, code_hash, attempts, expires_at, claimed_at
                FROM device_pairings
                WHERE code_hash = %s AND claimed_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (hash_credential(clean_code),),
            )
        pairing = cursor.fetchone()
        if not pairing or pairing["claimed_at"] is not None:
            raise ValueError("Pairing code is invalid or already used")
        if pairing["expires_at"] <= datetime.now(UTC):
            raise ValueError("Pairing code has expired")
        if int(pairing["attempts"] or 0) >= 5:
            raise ValueError("Pairing code attempts exceeded")
        if not hmac.compare_digest(str(pairing["code_hash"]), hash_credential(clean_code)):
            cursor.execute(
                "UPDATE device_pairings SET attempts = attempts + 1 WHERE pairing_id = %s",
                (pairing_id.strip(),),
            )
            raise ValueError("Pairing code is invalid")

        cursor.execute(
            "SELECT owner_user_id, status FROM devices WHERE device_id = %s FOR UPDATE",
            (pairing["device_id"],),
        )
        device = cursor.fetchone()
        if device and device["owner_user_id"] and device["owner_user_id"] != user_id:
            raise ValueError("Device is already bound to another account")
        credential, credential_hash = issue_device_credential()
        cursor.execute(
            """
            UPDATE devices
            SET owner_user_id = %s, status = 'offline', bound_at = COALESCE(bound_at, NOW()), updated_at = NOW()
            WHERE device_id = %s
            """,
            (user_id, pairing["device_id"]),
        )
        cursor.execute(
            """
            INSERT INTO device_credentials (device_id, credential_hash)
            VALUES (%s, %s)
            """,
            (pairing["device_id"], credential_hash),
        )
        cursor.execute(
            """
            UPDATE device_pairings
            SET claimed_at = NOW(), claimed_by_user_id = %s
            WHERE pairing_id = %s
            """,
            (user_id, pairing_id.strip()),
        )
    return {
        "device_id": pairing["device_id"],
        "client_id": pairing["client_id"],
        "credential": credential,
    }


def list_user_devices(user_id: str) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT device_id, client_id, display_name, firmware_version, status,
                   last_seen_at, wifi_ssid, bound_at, created_at, updated_at
            FROM devices WHERE owner_user_id = %s AND status != 'revoked'
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
    return [_device_row(row) for row in rows]


def get_user_device(user_id: str, device_id: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT device_id, client_id, display_name, firmware_version, status,
                   last_seen_at, wifi_ssid, bound_at, created_at, updated_at
            FROM devices WHERE owner_user_id = %s AND device_id = %s
            """,
            (user_id, normalize_device_id(device_id)),
        )
        return _device_row(cursor.fetchone())


def update_user_device(user_id: str, device_id: str, *, display_name: str | None = None) -> dict | None:
    clean_name = (display_name or "").strip()
    if not clean_name or len(clean_name) > 40:
        raise ValueError("display_name must contain 1-40 characters")
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """UPDATE devices SET display_name = %s, updated_at = NOW()
               WHERE owner_user_id = %s AND device_id = %s
               RETURNING device_id, client_id, display_name, firmware_version, status,
                         last_seen_at, wifi_ssid, bound_at, created_at, updated_at""",
            (clean_name, user_id, normalize_device_id(device_id)),
        )
        return _device_row(cursor.fetchone())


def unbind_user_device(user_id: str, device_id: str) -> bool:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """UPDATE devices SET owner_user_id = NULL, status = 'unclaimed', bound_at = NULL, updated_at = NOW()
               WHERE owner_user_id = %s AND device_id = %s
               RETURNING device_id""",
            (user_id, normalize_device_id(device_id)),
        )
        changed = cursor.fetchone() is not None
        if changed:
            cursor.execute(
                "UPDATE device_credentials SET status = 'revoked', revoked_at = NOW() WHERE device_id = %s AND status = 'active'",
                (normalize_device_id(device_id),),
            )
        return changed


def rotate_device_credential(user_id: str, device_id: str) -> str | None:
    raw, credential_hash = issue_device_credential()
    clean_device_id = normalize_device_id(device_id)
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT device_id FROM devices WHERE owner_user_id = %s AND device_id = %s FOR UPDATE",
            (user_id, clean_device_id),
        )
        if cursor.fetchone() is None:
            return None
        cursor.execute(
            "UPDATE device_credentials SET status = 'revoked', revoked_at = NOW() WHERE device_id = %s AND status = 'active'",
            (clean_device_id,),
        )
        cursor.execute(
            "INSERT INTO device_credentials (device_id, credential_hash) VALUES (%s, %s)",
            (clean_device_id, credential_hash),
        )
    return raw


def authenticate_database_device(device_id: str, client_id: str, credential: str) -> str | None:
    clean_device_id = normalize_device_id(device_id)
    clean_client_id = normalize_client_id(client_id)
    if not clean_device_id or not credential.strip():
        return None
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT d.owner_user_id, d.client_id, d.status, c.id
            FROM devices d JOIN device_credentials c ON c.device_id = d.device_id
            WHERE d.device_id = %s AND c.credential_hash = %s AND c.status = 'active'
            FOR UPDATE
            """,
            (clean_device_id, hash_credential(credential)),
        )
        row = cursor.fetchone()
        if not row or not row["owner_user_id"] or row["status"] == 'revoked':
            return None
        if row["client_id"] and clean_client_id and normalize_client_id(row["client_id"]) != clean_client_id:
            return None
        cursor.execute(
            "UPDATE device_credentials SET last_used_at = NOW() WHERE id = %s",
            (row["id"],),
        )
        return str(row["owner_user_id"])


def validate_device_credential(device_id: str, client_id: str, credential: str) -> dict | None:
    clean_device_id = normalize_device_id(device_id)
    clean_client_id = normalize_client_id(client_id)
    if not clean_device_id or not credential.strip():
        return None
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT d.device_id, d.client_id, d.owner_user_id, d.status, c.id
            FROM devices d JOIN device_credentials c ON c.device_id = d.device_id
            WHERE d.device_id = %s AND c.credential_hash = %s AND c.status = 'active'
            FOR UPDATE
            """,
            (clean_device_id, hash_credential(credential)),
        )
        row = cursor.fetchone()
        if not row or row["status"] == "revoked":
            return None
        if row["client_id"] and clean_client_id and normalize_client_id(row["client_id"]) != clean_client_id:
            return None
        cursor.execute("UPDATE device_credentials SET last_used_at = NOW() WHERE id = %s", (row["id"],))
        return dict(row)


def ensure_bootstrap_credential(*, device_id: str) -> str:
    clean_device_id = normalize_device_id(device_id)
    raw, credential_hash = issue_device_credential()
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT credential_hash FROM device_credentials WHERE device_id = %s AND status = 'active' LIMIT 1",
            (clean_device_id,),
        )
        if cursor.fetchone() is not None:
            return ""
        cursor.execute(
            "INSERT INTO device_credentials (device_id, credential_hash) VALUES (%s, %s)",
            (clean_device_id, credential_hash),
        )
    return raw


def touch_device(*, device_id: str, client_id: str, firmware_version: str = "", wifi_ssid: str = "", online: bool = True) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO devices (device_id, client_id, firmware_version, status, last_seen_at, wifi_ssid)
            VALUES (%s, %s, %s, %s, NOW(), %s)
            ON CONFLICT (device_id) DO UPDATE SET
                client_id = COALESCE(NULLIF(EXCLUDED.client_id, ''), devices.client_id),
                firmware_version = COALESCE(NULLIF(EXCLUDED.firmware_version, ''), devices.firmware_version),
                status = CASE WHEN devices.owner_user_id IS NULL THEN devices.status ELSE EXCLUDED.status END,
                last_seen_at = NOW(), wifi_ssid = COALESCE(NULLIF(EXCLUDED.wifi_ssid, ''), devices.wifi_ssid),
                updated_at = NOW()
            """,
            (normalize_device_id(device_id), normalize_client_id(client_id), firmware_version.strip(), 'online' if online else 'offline', wifi_ssid.strip()),
        )


def get_speaker_profile(user_id: str, device_id: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT speaker_profile_id, display_name, role, embedding, model_name, model_version, verification_threshold, status, created_at, updated_at FROM speaker_profiles WHERE owner_user_id = %s AND device_id = %s AND status = 'active'",
            (user_id, normalize_device_id(device_id)),
        )
        row = cursor.fetchone()
    return _device_row(row)


def get_device_speaker_profile(device_id: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT speaker_profile_id, owner_user_id, device_id, embedding, verification_threshold, status FROM speaker_profiles WHERE device_id = %s AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (normalize_device_id(device_id),),
        )
        return cursor.fetchone()


def save_speaker_sample(*, user_id: str, device_id: str, embedding: list[float], quality_score: float, duration_ms: int) -> dict:
    clean_device_id = normalize_device_id(device_id)
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT speaker_profile_id, embedding FROM speaker_profiles WHERE owner_user_id = %s AND device_id = %s AND status = 'active' FOR UPDATE",
            (user_id, clean_device_id),
        )
        profile = cursor.fetchone()
        profile_id = str(profile["speaker_profile_id"]) if profile else f"speaker_{uuid.uuid4().hex}"
        previous = profile.get("embedding") if profile else None
        previous = previous if isinstance(previous, list) else []
        vectors = [previous, embedding] if previous else [embedding]
        merged = [sum(vector[index] for vector in vectors) / len(vectors) for index in range(len(embedding))]
        if profile:
            cursor.execute(
                "UPDATE speaker_profiles SET embedding = %s::jsonb, updated_at = NOW() WHERE speaker_profile_id = %s",
                (json.dumps(merged), profile_id),
            )
        else:
            cursor.execute(
                "INSERT INTO speaker_profiles (speaker_profile_id, owner_user_id, device_id, embedding) VALUES (%s, %s, %s, %s::jsonb)",
                (profile_id, user_id, clean_device_id, json.dumps(merged)),
            )
        cursor.execute(
            "INSERT INTO speaker_enrollment_samples (speaker_profile_id, audio_duration_ms, quality_score, embedding) VALUES (%s, %s, %s, %s::jsonb)",
            (profile_id, duration_ms, quality_score, json.dumps(embedding)),
        )
    return {"speaker_profile_id": profile_id, "samples_added": 1}


def delete_speaker_profile(user_id: str, device_id: str) -> bool:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE speaker_profiles SET status = 'revoked', updated_at = NOW() WHERE owner_user_id = %s AND device_id = %s AND status = 'active' RETURNING speaker_profile_id",
            (user_id, normalize_device_id(device_id)),
        )
        return cursor.fetchone() is not None


def list_speaker_profile(user_id: str, device_id: str) -> dict | None:
    profile = get_speaker_profile(user_id, device_id)
    if profile is None:
        return None
    profile.pop("embedding", None)
    return profile


def record_voice_turn(*, device_id: str, user_id: str | None, request_id: str, speaker: dict[str, object], asr_text: str, audio_duration_ms: int) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO device_voice_turns (device_id, user_id, request_id, speaker_profile_id, speaker_role, speaker_confidence, verification_status, asr_text, audio_duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (request_id) DO UPDATE SET
                speaker_profile_id = EXCLUDED.speaker_profile_id, speaker_role = EXCLUDED.speaker_role,
                speaker_confidence = EXCLUDED.speaker_confidence, verification_status = EXCLUDED.verification_status,
                asr_text = EXCLUDED.asr_text, audio_duration_ms = EXCLUDED.audio_duration_ms
            """,
            (device_id, user_id, request_id, speaker.get("speaker_profile_id"), speaker.get("speaker_role", "unknown"), float(speaker.get("confidence", 0.0)), speaker.get("status", "unknown"), asr_text, audio_duration_ms),
        )


def update_voice_turn_messages(
    *,
    request_id: str,
    user_message_id: int | None,
    assistant_message_id: int | None,
) -> None:
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE device_voice_turns
            SET user_message_id = COALESCE(%s, user_message_id),
                assistant_message_id = COALESCE(%s, assistant_message_id)
            WHERE request_id = %s
            """,
            (user_message_id, assistant_message_id, request_id),
        )
