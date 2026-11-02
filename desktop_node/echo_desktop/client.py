from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import socket
import uuid

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from echo_desktop.config import DesktopConfig
from echo_desktop.executor import execute_command
from echo_desktop.protocol import ActionError, parse_command, result_payload

CAPABILITIES = ["open_app", "media_control", "screen_capture", "camera_capture"]


class DesktopAuthenticationError(RuntimeError):
    pass


def machine_fingerprint() -> str:
    raw = f"{platform.node()}|{uuid.getnode()}|{socket.gethostname()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def pair_node(
    *,
    server_url: str,
    code: str,
    node_name: str,
) -> DesktopConfig:
    base = server_url.rstrip("/")
    response = httpx.post(
        f"{base}/desktop/nodes/pair",
        json={
            "code": code,
            "name": node_name,
            "fingerprint": machine_fingerprint(),
            "capabilities": CAPABILITIES,
        },
        timeout=20,
    )
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"配对失败：{detail}")
    payload = response.json()
    return DesktopConfig(
        server_url=base,
        node_id=str(payload["node_id"]),
        node_name=str(payload["name"]),
        token=str(payload["token"]),
    )


async def _session(config: DesktopConfig) -> None:
    headers = {"Authorization": f"Bearer {config.token}"}
    async with connect(
        config.websocket_url,
        additional_headers=headers,
        ping_interval=20,
        ping_timeout=20,
        open_timeout=20,
        max_size=8 * 1024 * 1024,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "hello",
                    "node_id": config.node_id,
                    "name": config.node_name,
                    "capabilities": CAPABILITIES,
                },
                ensure_ascii=False,
            )
        )
        print(f"[Echo Desktop] 已连接 {config.server_url}，等待 Echo 的电脑操作。")
        async for raw in websocket:
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            message_type = payload.get("type")
            if message_type == "hello_ack":
                print(f"[Echo Desktop] 服务端已确认节点 {config.node_id}。")
                continue
            if message_type == "pong":
                continue
            if message_type != "command":
                continue
            try:
                command = parse_command(payload)
            except ValueError:
                continue
            print(f"[Echo Desktop] 请求操作：{command.action}")
            try:
                data = await execute_command(command)
            except ActionError as exc:
                await websocket.send(json.dumps(result_payload(command.command_id, error=exc)))
                print(f"[Echo Desktop] 操作未完成：{exc.code}")
            except Exception as exc:
                await websocket.send(
                    json.dumps(
                        result_payload(
                            command.command_id,
                            error=ActionError("action_failed", str(exc)),
                        ),
                        ensure_ascii=False,
                    )
                )
                print(f"[Echo Desktop] 操作异常：{type(exc).__name__}")
            else:
                await websocket.send(
                    json.dumps(
                        result_payload(command.command_id, data=data),
                        ensure_ascii=False,
                    )
                )
                print(f"[Echo Desktop] 操作完成：{command.action}")


async def run_node(config: DesktopConfig) -> None:
    delay = 2
    while True:
        try:
            await _session(config)
            print("[Echo Desktop] 连接已断开，准备重连。")
        except ConnectionClosed as exc:
            if exc.code == 4401:
                raise DesktopAuthenticationError("电脑节点 token 已失效，请重新配对。") from exc
            print(f"[Echo Desktop] 连接断开（{exc.code}），{delay} 秒后重连。")
        except DesktopAuthenticationError:
            raise
        except Exception as exc:
            print(f"[Echo Desktop] 连接失败：{type(exc).__name__}，{delay} 秒后重试。")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
