from __future__ import annotations

import argparse
import asyncio
import platform
import sys

from echo_desktop.client import CAPABILITIES, pair_node, run_node
from echo_desktop.config import clear_config, config_path, load_config, save_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="echo-desktop",
        description="Echo Desktop 电脑节点（Windows MVP）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pair = subparsers.add_parser("pair", help="用配对码绑定这台电脑")
    pair.add_argument("--code", required=True, help="服务端生成的一次性配对码")
    pair.add_argument("--name", default=platform.node() or "我的电脑")
    pair.add_argument("--server", default="https://api.echoaiforever.cn")

    subparsers.add_parser("run", help="连接 Echo 并等待电脑操作")
    subparsers.add_parser("status", help="查看本机配对状态")
    subparsers.add_parser("logout", help="删除本机保存的节点 token")
    return parser


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Echo Desktop MVP 目前只支持 Windows。")
    args = _build_parser().parse_args()
    if args.command == "pair":
        config = pair_node(
            server_url=args.server,
            code=args.code,
            node_name=args.name,
        )
        save_config(config)
        print(f"配对成功：{config.node_name} ({config.node_id})")
        print(f"配置已保存到：{config_path()}")
        print("现在运行：python -m echo_desktop run")
        return
    if args.command == "run":
        config = load_config()
        if config is None:
            raise SystemExit("还没有配对。先运行 python -m echo_desktop pair --code <配对码>")
        print(f"节点：{config.node_name} ({config.node_id})")
        print(f"能力：{', '.join(CAPABILITIES)}")
        try:
            asyncio.run(run_node(config))
        except KeyboardInterrupt:
            print("\n已停止 Echo Desktop。")
        return
    if args.command == "status":
        config = load_config()
        if config is None:
            print("未配对")
            return
        print(f"node_id={config.node_id}")
        print(f"name={config.node_name}")
        print(f"server={config.server_url}")
        return
    if args.command == "logout":
        clear_config()
        print("已删除本机保存的配对信息；服务端设备仍需在账号中断开。")


__all__ = ["main"]
