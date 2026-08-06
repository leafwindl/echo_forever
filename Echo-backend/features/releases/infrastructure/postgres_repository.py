from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from db.postgres_connection import get_connection, transaction

from features.releases.domain.entities import AppRelease


def _release(row) -> AppRelease:
    notes = row["release_notes"] or []
    if isinstance(notes, str):
        notes = json.loads(notes)
    return AppRelease(
        release_id=row["release_id"],
        platform=row["platform"],
        channel=row["channel"],
        package_name=row["package_name"],
        version_name=row["version_name"],
        version_code=int(row["version_code"]),
        minimum_version_code=int(row["minimum_version_code"]),
        cos_object_key=row["cos_object_key"],
        sha256=row["sha256"],
        size_bytes=int(row["size_bytes"]),
        release_notes=tuple(str(note) for note in notes),
        mandatory=bool(row["mandatory"]),
        status=row["status"],
        published_at=row["published_at"],
    )


class PostgresReleaseRepository:
    def get_by_version(self, platform: str, channel: str, version_code: int) -> AppRelease | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM app_releases
                WHERE platform=%s AND channel=%s AND version_code=%s
                """,
                (platform, channel, version_code),
            )
            row = cursor.fetchone()
        return _release(row) if row else None

    def find_latest(self, platform: str, channel: str) -> AppRelease | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM app_releases
                WHERE platform=%s AND channel=%s AND status='active'
                ORDER BY version_code DESC LIMIT 1
                """,
                (platform, channel),
            )
            row = cursor.fetchone()
        return _release(row) if row else None

    def get_active(self, release_id: str, platform: str, channel: str) -> AppRelease | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM app_releases
                WHERE release_id=%s AND platform=%s AND channel=%s AND status='active'
                """,
                (release_id, platform, channel),
            )
            row = cursor.fetchone()
        return _release(row) if row else None

    def publish(
        self,
        *,
        platform: str,
        channel: str,
        package_name: str,
        version_name: str,
        version_code: int,
        minimum_version_code: int,
        cos_object_key: str,
        sha256: str,
        size_bytes: int,
        release_notes: Sequence[str],
        mandatory: bool,
    ) -> AppRelease:
        release_id = f"release_{uuid.uuid4().hex}"
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app_releases (
                    release_id, platform, channel, package_name, version_name,
                    version_code, minimum_version_code, cos_object_key, sha256,
                    size_bytes, release_notes, mandatory, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'draft')
                """,
                (
                    release_id,
                    platform,
                    channel,
                    package_name,
                    version_name,
                    version_code,
                    minimum_version_code,
                    cos_object_key,
                    sha256,
                    size_bytes,
                    json.dumps(list(release_notes), ensure_ascii=False),
                    mandatory,
                ),
            )
            cursor.execute(
                """
                UPDATE app_releases
                SET status='active', published_at=NOW(), updated_at=NOW()
                WHERE release_id=%s RETURNING *
                """,
                (release_id,),
            )
            row = cursor.fetchone()
        return _release(row)
