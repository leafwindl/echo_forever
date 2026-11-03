from __future__ import annotations

from datetime import datetime
from typing import Any

from db.postgres_connection import get_connection, transaction

from features.mobile_agent.domain.entities import MobileAgentDevice


def _device(row: dict[str, Any]) -> MobileAgentDevice:
    return MobileAgentDevice(
        device_id=str(row["device_id"]),
        user_id=str(row["user_id"]),
        name=str(row["name"]),
        status=str(row["status"]),
        last_seen_at=row.get("last_seen_at"),
        created_at=row.get("created_at"),
    )


class PostgresMobileAgentRepository:
    def create_pairing_code(
        self, *, code_hash: str, user_id: str, expires_at: datetime
    ) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO mobile_agent_pairing_codes (code_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (code_hash) DO NOTHING
                """,
                (code_hash, user_id, expires_at),
            )
            return cursor.rowcount == 1

    def pair_device(
        self,
        *,
        code_hash: str,
        device_name: str,
        token_hash: str,
        device_id: str,
        now: datetime,
    ) -> MobileAgentDevice | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, expires_at, consumed_at
                FROM mobile_agent_pairing_codes
                WHERE code_hash = %s
                FOR UPDATE
                """,
                (code_hash,),
            )
            pairing = cursor.fetchone()
            if pairing is None:
                return None
            if pairing["consumed_at"] is not None or pairing["expires_at"] <= now:
                return None
            cursor.execute(
                """
                UPDATE mobile_agent_pairing_codes
                SET consumed_at = NOW(), attempts = attempts + 1
                WHERE code_hash = %s
                """,
                (code_hash,),
            )
            cursor.execute(
                """
                INSERT INTO mobile_agent_devices (
                    device_id, user_id, name, token_hash, status
                ) VALUES (%s, %s, %s, %s, 'offline')
                RETURNING *
                """,
                (device_id, pairing["user_id"], device_name, token_hash),
            )
            return _device(cursor.fetchone())

    def find_by_token_hash(self, token_hash: str) -> MobileAgentDevice | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM mobile_agent_devices
                WHERE token_hash = %s AND status <> 'revoked'
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            return _device(row) if row else None

    def list_devices(self, user_id: str) -> list[MobileAgentDevice]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM mobile_agent_devices
                WHERE user_id = %s AND status <> 'revoked'
                ORDER BY last_seen_at DESC NULLS LAST, created_at DESC
                """,
                (user_id,),
            )
            return [_device(row) for row in cursor.fetchall()]

    def revoke_device(self, user_id: str, device_id: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mobile_agent_devices
                SET status = 'revoked', updated_at = NOW()
                WHERE user_id = %s AND device_id = %s AND status <> 'revoked'
                """,
                (user_id, device_id),
            )
            return cursor.rowcount == 1

    def mark_online(self, device_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mobile_agent_devices
                SET status = 'online', last_seen_at = NOW(), updated_at = NOW()
                WHERE device_id = %s AND status <> 'revoked'
                """,
                (device_id,),
            )

    def mark_offline(self, device_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mobile_agent_devices
                SET status = 'offline', last_seen_at = NOW(), updated_at = NOW()
                WHERE device_id = %s AND status <> 'revoked'
                """,
                (device_id,),
            )
