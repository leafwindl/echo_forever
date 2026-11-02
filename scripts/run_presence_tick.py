from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from db.postgres_connection import get_connection  # noqa: E402
from features.presence.public import (  # noqa: E402
    get_presence_state,
    list_presence_thoughts,
    run_presence_tick,
)
from shared.config import settings  # noqa: E402


def _resolve_user(phone: str, user_id: str) -> str:
    if user_id.strip():
        return user_id.strip()
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT user_id FROM users WHERE phone = %s", (phone.strip(),))
        row = cursor.fetchone()
    if row is None:
        raise SystemExit(f"没有找到手机号对应的用户：{phone}")
    return str(row["user_id"])


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run one Echo presence heartbeat")
    parser.add_argument("--phone", default="")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.phone and not args.user_id:
        parser.error("--phone or --user-id is required")
    user_id = _resolve_user(args.phone, args.user_id)
    result = await run_presence_tick(user_id)
    state = get_presence_state(user_id)
    thoughts = list_presence_thoughts(user_id, args.limit)
    print(f"user_id={user_id}")
    print(f"status={result.status}")
    print(f"decision={result.decision} reason={result.reason}")
    print(f"thoughts_used={state.thoughts_used}/{settings.presence_daily_thought_budget}")
    if result.thought:
        print(f"new_thought={result.thought.text}")
    for thought in thoughts:
        print(
            f"- {thought.created_at.isoformat() if thought.created_at else ''} "
            f"salience={thought.salience:.2f} {thought.text}"
        )


if __name__ == "__main__":
    asyncio.run(_main())
