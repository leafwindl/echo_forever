import json
from dataclasses import replace
from datetime import datetime
from typing import Any

from db.postgres_connection import get_connection, transaction

from features.persona.domain.entities import PersonaUpdate, UserPersona, build_user_persona


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _topics_from_database(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _persona_from_row(row: dict[str, Any]) -> UserPersona:
    persona = build_user_persona(
        str(row["user_id"]),
        PersonaUpdate(
            preferred_name=row.get("preferred_name"),
            reply_style=str(row["reply_style"]),
            reply_length=str(row["reply_length"]),
            support_mode=str(row["support_mode"]),
            proactivity=str(row["proactivity"]),
            avoid_topics=_topics_from_database(row.get("avoid_topics")),
            about_user=row.get("about_user"),
            enabled=bool(row["enabled"]),
        ),
        is_customized=True,
    )
    return replace(
        persona,
        schema_version=int(row.get("schema_version") or 1),
        created_at=_timestamp_text(row.get("created_at")),
        updated_at=_timestamp_text(row.get("updated_at")),
    )


class PostgresPersonaRepository:
    """PostgreSQL Persona 仓储；所有查询均以 user_id 隔离。"""

    def get(self, user_id: str) -> UserPersona | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, preferred_name, reply_style, reply_length,
                       support_mode, proactivity, avoid_topics, about_user,
                       enabled, schema_version, created_at, updated_at
                FROM user_personas
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return _persona_from_row(row) if row else None

    def save(self, persona: UserPersona) -> UserPersona:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_personas (
                    user_id, preferred_name, reply_style, reply_length,
                    support_mode, proactivity, avoid_topics, about_user,
                    enabled, schema_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    preferred_name = EXCLUDED.preferred_name,
                    reply_style = EXCLUDED.reply_style,
                    reply_length = EXCLUDED.reply_length,
                    support_mode = EXCLUDED.support_mode,
                    proactivity = EXCLUDED.proactivity,
                    avoid_topics = EXCLUDED.avoid_topics,
                    about_user = EXCLUDED.about_user,
                    enabled = EXCLUDED.enabled,
                    schema_version = EXCLUDED.schema_version,
                    updated_at = NOW()
                RETURNING user_id, preferred_name, reply_style, reply_length,
                          support_mode, proactivity, avoid_topics, about_user,
                          enabled, schema_version, created_at, updated_at
                """,
                (
                    persona.user_id,
                    persona.preferred_name,
                    persona.reply_style,
                    persona.reply_length,
                    persona.support_mode,
                    persona.proactivity,
                    json.dumps(persona.avoid_topics, ensure_ascii=False),
                    persona.about_user,
                    persona.enabled,
                    persona.schema_version,
                ),
            )
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("Persona upsert returned no row")
        return _persona_from_row(row)

    def delete(self, user_id: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_personas WHERE user_id = %s", (user_id,))
            deleted = cursor.rowcount
        return bool(deleted)
