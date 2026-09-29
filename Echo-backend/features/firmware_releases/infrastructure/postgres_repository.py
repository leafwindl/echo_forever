from __future__ import annotations

import json
import uuid

from db.postgres_connection import get_connection, transaction

from features.firmware_releases.domain.entities import FirmwareRelease


def _release(row) -> FirmwareRelease:
    notes = row["release_notes"] or []
    if isinstance(notes, str):
        notes = json.loads(notes)
    return FirmwareRelease(
        release_id=row["release_id"],
        board_type=row["board_type"],
        board_variant=row["board_variant"],
        version=row["version"],
        cos_object_key=row["cos_object_key"],
        sha256=row["sha256"],
        size_bytes=int(row["size_bytes"]),
        release_notes=tuple(str(note) for note in notes),
        status=row["status"],
        published_at=row["published_at"],
    )


class PostgresFirmwareReleaseRepository:
    def find_latest(self, board_type: str, board_variant: str = "") -> FirmwareRelease | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM firmware_releases
                WHERE board_type=%s AND status='active'
                  AND (board_variant=%s OR board_variant='')
                """,
                (board_type, board_variant),
            )
            rows = cursor.fetchall()
        releases = [_release(row) for row in rows]
        return max(
            releases,
            key=lambda release: (
                release.board_variant == board_variant,
                tuple(int(part) if part.isdigit() else 0 for part in release.version.split(".")),
            ),
            default=None,
        )

    def get_by_version(self, board_type: str, board_variant: str, version: str) -> FirmwareRelease | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM firmware_releases WHERE board_type=%s AND board_variant=%s AND version=%s",
                (board_type, board_variant, version),
            )
            row = cursor.fetchone()
        return _release(row) if row else None

    def publish(self, *, board_type: str, board_variant: str, version: str, cos_object_key: str, sha256: str, size_bytes: int, release_notes: list[str]) -> FirmwareRelease:
        release_id = f"firmware_{uuid.uuid4().hex}"
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO firmware_releases (release_id, board_type, board_variant, version, cos_object_key, sha256, size_bytes, release_notes, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'active') RETURNING *
                """,
                (release_id, board_type, board_variant, version, cos_object_key, sha256, size_bytes, json.dumps(release_notes, ensure_ascii=False)),
            )
            row = cursor.fetchone()
        return _release(row)
