import argparse
import shutil
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


def create_pre_restore_backup(current_db_path: Path, backup_dir: Path) -> Path | None:
    if not current_db_path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{current_db_path.stem}_pre_restore_{timestamp}.db"

    with sqlite3.connect(str(current_db_path)) as source_conn:
        with sqlite3.connect(str(backup_path)) as backup_conn:
            source_conn.backup(backup_conn)

    verify_sqlite_database(backup_path)
    return backup_path


def restore_database(source_backup_path: Path, target_db_path: Path, backup_dir: Path) -> Path | None:
    if not source_backup_path.exists():
        raise FileNotFoundError(f"Backup file does not exist: {source_backup_path}")

    verify_sqlite_database(source_backup_path)
    pre_restore_backup_path = create_pre_restore_backup(target_db_path, backup_dir)
    target_db_path.parent.mkdir(parents=True, exist_ok=True)

    for suffix in ("-wal", "-shm"):
        sidecar_path = Path(f"{target_db_path}{suffix}")
        if sidecar_path.exists():
            sidecar_path.unlink()

    shutil.copy2(source_backup_path, target_db_path)
    verify_sqlite_database(target_db_path)
    return pre_restore_backup_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore Echo SQLite database from a verified backup.")
    parser.add_argument("backup", type=Path, help="Backup db file to restore from.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Target SQLite database path.")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory to store pre-restore backup files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pre_restore_backup_path = restore_database(
        args.backup.resolve(),
        args.db.resolve(),
        args.backup_dir.resolve(),
    )
    if pre_restore_backup_path:
        print(f"Pre-restore backup created: {pre_restore_backup_path}")
    print(f"Database restored: {args.db.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
