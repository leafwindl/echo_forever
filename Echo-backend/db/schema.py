from db.postgres_connection import transaction
from db.postgres_schema import build_postgres_schema_sql
from shared.config import settings


def init_db() -> None:
    """初始化 PostgreSQL + pgvector schema。"""
    with transaction() as conn:
        with conn.cursor() as cursor:
            for statement in build_postgres_schema_sql(settings.embedding_vector_dimension):
                cursor.execute(statement)
