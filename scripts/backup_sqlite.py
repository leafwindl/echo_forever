import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "echo_memory.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


def verify_sqlite_database(database_path: Path) -> None:
    with sqlite3.connect(str(database_path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity_check failed for {database_path}: {result}")


def backup_database(source_path: Path, backup_dir: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{source_path.stem}_{timestamp}.db"

    with sqlite3.connect(str(source_path)) as source_conn:
        with sqlite3.connect(str(backup_path)) as backup_conn:
            source_conn.backup(backup_conn)

    verify_sqlite_database(backup_path)
    return backup_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up Echo SQLite database safely.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory to store backup db files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backup_path = backup_database(args.db.resolve(), args.backup_dir.resolve())
    print(f"Backup created: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
