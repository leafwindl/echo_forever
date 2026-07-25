from contextlib import contextmanager
from typing import Iterator

from shared.config import settings


def get_database_url() -> str:
    database_url = settings.database_url.strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when DB_PROVIDER=postgres")
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


@contextmanager
def get_connection() -> Iterator:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        yield conn


@contextmanager
def transaction() -> Iterator:
    with get_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
