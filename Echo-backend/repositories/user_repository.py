import sqlite3
from typing import Optional

from db.connection import transaction


def upsert_user(
    user_id: str,
    openid: Optional[str] = None,
    nickname: Optional[str] = None,
    avatar_url: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
):
    if conn is None:
        with transaction() as tx:
            return upsert_user(user_id, openid, nickname, avatar_url, conn=tx)

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (user_id, openid, nickname, avatar_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            openid = COALESCE(excluded.openid, users.openid),
            nickname = COALESCE(excluded.nickname, users.nickname),
            avatar_url = COALESCE(excluded.avatar_url, users.avatar_url),
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, openid, nickname, avatar_url),
    )
