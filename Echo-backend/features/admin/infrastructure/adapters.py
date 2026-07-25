from db.postgres_connection import get_connection, transaction
from features.admin.domain.services import ChatContextAdminRepository, RuntimeSettingsRepository


class PostgresRuntimeSettingsRepository(RuntimeSettingsRepository):
    def get_value(self, key: str) -> str | None:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT value
                    FROM runtime_settings
                    WHERE key = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        return str(row["value"]) if row else None

    def set_value(self, key: str, value: str) -> None:
        with transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runtime_settings (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT(key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    (key, value),
                )


class PostgresChatContextAdminRepository(ChatContextAdminRepository):
    def clear_user_chat_context(self, user_id: str) -> tuple[int, int]:
        with transaction() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM chat_messages WHERE user_id = %s", (user_id,))
                deleted_messages = cursor.rowcount if cursor.rowcount >= 0 else 0

                cursor.execute(
                    """
                    UPDATE conversations
                    SET summary = '',
                        summary_message_id = 0,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                reset_conversations = cursor.rowcount if cursor.rowcount >= 0 else 0

        return deleted_messages, reset_conversations
