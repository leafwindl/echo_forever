from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from db.postgres_connection import get_connection, transaction
from psycopg.types.json import Jsonb

from features.desktop.domain.entities import DesktopNode


def _node(row: dict[str, Any]) -> DesktopNode:
    capabilities = row.get("capabilities") or []
    if isinstance(capabilities, str):
        capabilities = json.loads(capabilities)
    return DesktopNode(
        node_id=str(row["node_id"]),
        user_id=str(row["user_id"]),
        name=str(row["name"]),
        capabilities=tuple(str(item) for item in capabilities),
        status=str(row["status"]),
        last_seen_at=row.get("last_seen_at"),
        created_at=row.get("created_at"),
    )


class PostgresDesktopRepository:
    def create_pairing_code(
        self,
        *,
        code_hash: str,
        user_id: str,
        expires_at: datetime,
    ) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO desktop_pairing_codes (code_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (code_hash) DO NOTHING
                """,
                (code_hash, user_id, expires_at),
            )
            return cursor.rowcount == 1

    def pair_node(
        self,
        *,
        code_hash: str,
        node_name: str,
        fingerprint: str,
        token_hash: str,
        node_id: str,
        capabilities: tuple[str, ...],
        now: datetime,
    ) -> DesktopNode | None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, expires_at, consumed_at
                FROM desktop_pairing_codes
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
                UPDATE desktop_pairing_codes
                SET consumed_at = NOW(), attempts = attempts + 1
                WHERE code_hash = %s
                """,
                (code_hash,),
            )
            cursor.execute(
                """
                INSERT INTO desktop_nodes (
                    node_id, user_id, name, fingerprint, token_hash,
                    capabilities, status, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'offline', NULL)
                RETURNING *
                """,
                (
                    node_id,
                    pairing["user_id"],
                    node_name,
                    fingerprint,
                    token_hash,
                    Jsonb(list(capabilities)),
                ),
            )
            return _node(cursor.fetchone())

    def find_node_by_token_hash(self, token_hash: str) -> DesktopNode | None:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM desktop_nodes
                WHERE token_hash = %s AND status <> 'revoked'
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            return _node(row) if row else None

    def list_nodes(self, user_id: str) -> list[DesktopNode]:
        with get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM desktop_nodes
                WHERE user_id = %s AND status <> 'revoked'
                ORDER BY last_seen_at DESC NULLS LAST, created_at DESC
                """,
                (user_id,),
            )
            return [_node(row) for row in cursor.fetchall()]

    def revoke_node(self, user_id: str, node_id: str) -> bool:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE desktop_nodes
                SET status = 'revoked', updated_at = NOW()
                WHERE user_id = %s AND node_id = %s AND status <> 'revoked'
                """,
                (user_id, node_id),
            )
            return cursor.rowcount == 1

    def mark_online(self, node_id: str, capabilities: tuple[str, ...]) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE desktop_nodes
                SET status = 'online', capabilities = %s,
                    last_seen_at = NOW(), updated_at = NOW()
                WHERE node_id = %s AND status <> 'revoked'
                """,
                (Jsonb(list(capabilities)), node_id),
            )

    def mark_offline(self, node_id: str) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE desktop_nodes
                SET status = 'offline', last_seen_at = NOW(), updated_at = NOW()
                WHERE node_id = %s AND status <> 'revoked'
                """,
                (node_id,),
            )

    def record_action_start(
        self,
        *,
        action_id: str,
        node_id: str,
        user_id: str,
        action: str,
    ) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO desktop_actions (
                    action_id, node_id, user_id, action, status
                ) VALUES (%s, %s, %s, %s, 'running')
                """,
                (action_id, node_id, user_id, action),
            )

    def record_action_finish(
        self,
        *,
        action_id: str,
        status: str,
        error_code: str | None,
        duration_ms: int,
    ) -> None:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE desktop_actions
                SET status = %s, error_code = %s,
                    duration_ms = %s, completed_at = NOW()
                WHERE action_id = %s
                """,
                (status, error_code, duration_ms, action_id),
            )
