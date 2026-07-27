import logging

from db.postgres_connection import get_connection

logger = logging.getLogger(__name__)


def is_database_ready() -> bool:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
        return row is not None
    except Exception as exc:
        logger.warning("Database readiness check failed error_type=%s", type(exc).__name__)
        return False
