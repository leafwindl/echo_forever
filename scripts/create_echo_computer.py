from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from features.desktop.public import create_echo_computer  # noqa: E402

ECHO_COMPUTER_CAPABILITIES = (
    "screen_capture",
    "click",
    "type",
    "key",
    "open_app",
    "exec",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create (or re-key) an Echo-owned computer node for the VM agent"
    )
    parser.add_argument("--user-id", default="", help="Echo 用户 ID")
    parser.add_argument("--name", default="EchoComputer", help="节点名称")
    parser.add_argument(
        "--server-url",
        default="https://api.echoaiforever.cn",
        help="agent 连接的服务端地址",
    )
    parser.add_argument(
        "--output",
        default="",
        help="把配置写到文件（默认打印到 stdout）",
    )
    args = parser.parse_args()

    if not args.user_id.strip():
        parser.error("--user-id is required")

    paired = create_echo_computer(
        user_id=args.user_id.strip(),
        node_name=args.name,
        capabilities=ECHO_COMPUTER_CAPABILITIES,
    )
    config = {
        "server_url": args.server_url.rstrip("/"),
        "node_id": paired.node.node_id,
        "node_name": paired.node.name,
        "node_key": paired.token,
        "capabilities": list(ECHO_COMPUTER_CAPABILITIES),
    }
    text = json.dumps(config, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"written: {path}")
        print(f"node_id={config['node_id']} name={config['node_name']}")
    else:
        print(text)


if __name__ == "__main__":
    main()
