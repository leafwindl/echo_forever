from typing import Optional

from db.postgres_connection import transaction


def upsert_user(
    user_id: str,
    openid: Optional[str] = None,
    nickname: Optional[str] = None,
    avatar_url: Optional[str] = None,
    conn=None,
) -> None:
    if conn is None:
        with transaction() as tx:
            return upsert_user(user_id, openid, nickname, avatar_url, conn=tx)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (user_id, openid, nickname, avatar_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                openid = COALESCE(EXCLUDED.openid, users.openid),
                nickname = COALESCE(EXCLUDED.nickname, users.nickname),
                avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
                updated_at = NOW()
            """,
            (user_id, openid, nickname, avatar_url),
        )
