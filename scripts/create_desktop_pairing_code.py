from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from db.postgres_connection import get_connection  # noqa: E402
from features.desktop.public import create_desktop_pairing_code  # noqa: E402


def _resolve_user(phone: str, user_id: str) -> str:
    if user_id.strip():
        return user_id.strip()
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT user_id FROM users WHERE phone = %s", (phone.strip(),))
        row = cursor.fetchone()
    if row is None:
        raise SystemExit(f"没有找到手机号对应的用户：{phone}")
    return str(row["user_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a one-time Echo Desktop pairing code")
    parser.add_argument("--phone", default="", help="Echo 账号手机号，例如 +86137...")
    parser.add_argument("--user-id", default="", help="已知用户 ID 时可直接传入")
    args = parser.parse_args()
    if not args.phone and not args.user_id:
        parser.error("--phone or --user-id is required")
    user_id = _resolve_user(args.phone, args.user_id)
    pairing = create_desktop_pairing_code(user_id)
    print(f"user_id={user_id}")
    print(f"pairing_code={pairing.code}")
    print(f"expires_at={pairing.expires_at.isoformat()}")
    print("在电脑上运行：python -m echo_desktop pair --code <code>")


if __name__ == "__main__":
    main()
