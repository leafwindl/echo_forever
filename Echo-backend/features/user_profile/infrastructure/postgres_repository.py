from __future__ import annotations

import json
from datetime import UTC, datetime

from db.postgres_connection import get_connection, transaction

from features.user_profile.domain.entities import (
    PROFILE_DICT_FIELDS,
    PROFILE_LIST_FIELDS,
    PROFILE_TEXT_FIELDS,
    UserProfile,
)

_TEXT_LIMITS = {
    "display_name": 40,
    "personality": 600,
    "communication": 600,
    "notes": 1200,
}
_LIST_LIMIT = 20


class PostgresUserProfileRepository:
    def get(self, user_id: str) -> UserProfile | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
        return _profile(row) if row is not None else None

    def upsert_patch(self, user_id: str, patch: dict[str, object]) -> UserProfile:
        current = self.get(user_id)
        merged = _merge_profile(current, patch)
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_profiles (
                    user_id, display_name, basics, routine, personality, communication,
                    interests, boundaries, notes, confidence, updated_at
                ) VALUES (
                    %s, %s, %s::jsonb, %s::jsonb, %s, %s,
                    %s::jsonb, %s::jsonb, %s, %s::jsonb, NOW()
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    basics = EXCLUDED.basics,
                    routine = EXCLUDED.routine,
                    personality = EXCLUDED.personality,
                    communication = EXCLUDED.communication,
                    interests = EXCLUDED.interests,
                    boundaries = EXCLUDED.boundaries,
                    notes = EXCLUDED.notes,
                    confidence = EXCLUDED.confidence,
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    user_id,
                    merged.display_name,
                    json.dumps(merged.basics, ensure_ascii=False),
                    json.dumps(merged.routine, ensure_ascii=False),
                    merged.personality,
                    merged.communication,
                    json.dumps(list(merged.interests), ensure_ascii=False),
                    json.dumps(list(merged.boundaries), ensure_ascii=False),
                    merged.notes,
                    json.dumps(merged.confidence, ensure_ascii=False),
                ),
            )
            row = cursor.fetchone()
        return _profile(row)


def _merge_profile(current: UserProfile | None, patch: dict[str, object]) -> UserProfile:
    base = current or UserProfile(user_id="")
    values = {
        "display_name": base.display_name,
        "basics": dict(base.basics),
        "routine": dict(base.routine),
        "personality": base.personality,
        "communication": base.communication,
        "interests": list(base.interests),
        "boundaries": list(base.boundaries),
        "notes": base.notes,
        "confidence": dict(base.confidence),
    }
    for name in PROFILE_TEXT_FIELDS:
        value = patch.get(name)
        if isinstance(value, str) and value.strip():
            values[name] = value.strip()[:_TEXT_LIMITS.get(name, 600)]
    for name in PROFILE_DICT_FIELDS:
        value = patch.get(name)
        if isinstance(value, dict):
            merged_dict = dict(values[name])
            for key, item in value.items():
                if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip():
                    merged_dict[key.strip()[:40]] = item.strip()[:200]
            values[name] = merged_dict
    for name in PROFILE_LIST_FIELDS:
        value = patch.get(name)
        if isinstance(value, list):
            merged_list = list(values[name])
            for item in value:
                if isinstance(item, str) and item.strip() and item.strip() not in merged_list:
                    merged_list.append(item.strip()[:120])
            values[name] = merged_list[:_LIST_LIMIT]
    return UserProfile(
        user_id=base.user_id or str(patch.get("user_id") or ""),
        display_name=values["display_name"],
        basics=values["basics"],
        routine=values["routine"],
        personality=values["personality"],
        communication=values["communication"],
        interests=tuple(values["interests"]),
        boundaries=tuple(values["boundaries"]),
        notes=values["notes"],
        confidence=values["confidence"],
        updated_at=datetime.now(UTC),
    )


def _profile(row) -> UserProfile:
    def _json(value, fallback):
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    interests = _json(row["interests"], [])
    boundaries = _json(row["boundaries"], [])
    return UserProfile(
        user_id=str(row["user_id"]),
        display_name=str(row["display_name"] or ""),
        basics=_json(row["basics"], {}),
        routine=_json(row["routine"], {}),
        personality=str(row["personality"] or ""),
        communication=str(row["communication"] or ""),
        interests=tuple(str(item) for item in interests if str(item).strip()),
        boundaries=tuple(str(item) for item in boundaries if str(item).strip()),
        notes=str(row["notes"] or ""),
        confidence=_json(row["confidence"], {}),
        updated_at=row.get("updated_at"),
    )
