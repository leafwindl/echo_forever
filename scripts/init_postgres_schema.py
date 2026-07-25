import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))

from db.postgres_schema import build_postgres_schema_sql, build_postgres_schema_text


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(BACKEND_ROOT / ".env")


def _create_schema(database_url: str, vector_dimension: int) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: psycopg. Install requirements before initializing PostgreSQL."
        ) from exc

    statements = build_postgres_schema_sql(vector_dimension)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        conn.commit()


def main() -> int:
    _load_dotenv_if_available()

    parser = argparse.ArgumentParser(description="Initialize Echo PostgreSQL + pgvector schema.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument(
        "--vector-dimension",
        type=int,
        default=int(os.getenv("EMBEDDING_VECTOR_DIMENSION", "1024")),
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print schema SQL instead of executing it.",
    )
    args = parser.parse_args()

    if args.print_sql:
        print(build_postgres_schema_text(args.vector_dimension))
        return 0

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required unless --print-sql is used.")

    _create_schema(args.database_url, args.vector_dimension)
    print("PostgreSQL schema initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
