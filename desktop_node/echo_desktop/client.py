from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import socket
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from echo_desktop.config import DesktopConfig
from echo_desktop.executor import default_approval, execute_command
from echo_desktop.logging import append_log
from echo_desktop.protocol import ActionError, Command, parse_command, result_payload

CAPABILITIES = ["open_app", "media_control", "screen_capture", "camera_capture"]


class DesktopAuthenticationError(RuntimeError):
    pass


@dataclass
class RuntimeCallbacks:
    on_status: Callable[[str, str], None] = lambda _status, _detail: None
    on_log: Callable[[str, str], None] = lambda _level, _message: None
    on_action: Callable[[str, str, str], None] = lambda _action, _state, _detail: None


def _emit(callbacks: RuntimeCallbacks, level: str, message: str) -> None:
    append_log(level, message)
    callbacks.on_log(level, message)


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
    with httpx.Client(trust_env=False, timeout=20) as client:
        response = client.post(
            f"{base}/desktop/nodes/pair",
            json={
                "code": code,
                "name": node_name,
                "fingerprint": machine_fingerprint(),
                "capabilities": CAPABILITIES,
            },
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
        auto_approve=True,
    )


async def _always_allow(*_args, **_kwargs) -> bool:
    return True


class NodeRuntime:
    def __init__(
        self,
        config: DesktopConfig,
        *,
        callbacks: RuntimeCallbacks | None = None,
    ):
        self.config = config
        self.auto_approve = config.auto_approve
        self.callbacks = callbacks or RuntimeCallbacks()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._websocket = None
        self._stop_requested = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="echo-desktop-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        loop = self._loop
        websocket = self._websocket
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._close_websocket, websocket)
        self.callbacks.on_status("stopped", "已手动停止")
        _emit(self.callbacks, "INFO", "已请求停止电脑节点")

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_forever())
        except Exception as exc:
            self.callbacks.on_status("error", type(exc).__name__)
            _emit(self.callbacks, "ERROR", f"节点线程退出：{type(exc).__name__}")

    def _close_websocket(self, websocket) -> None:
        if websocket is not None:
            asyncio.ensure_future(websocket.close())

    async def _run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        delay = 2
        while not self._stop_requested.is_set():
            try:
                self.callbacks.on_status("connecting", self.config.server_url)
                await self._session()
                if self._stop_requested.is_set():
                    break
                self.callbacks.on_status("connecting", "连接已断开")
                _emit(self.callbacks, "WARN", "连接已断开，准备重连")
            except ConnectionClosed as exc:
                if exc.code == 4401:
                    self.callbacks.on_status("auth_error", "token 已失效")
                    _emit(self.callbacks, "ERROR", "节点 token 已失效，请重新配对")
                    return
                _emit(self.callbacks, "WARN", f"连接断开（{exc.code}），{delay} 秒后重连")
            except DesktopAuthenticationError:
                self.callbacks.on_status("auth_error", "token 已失效")
                _emit(self.callbacks, "ERROR", "节点 token 已失效，请重新配对")
                return
            except Exception as exc:
                _emit(
                    self.callbacks,
                    "ERROR",
                    f"连接失败：{type(exc).__name__}，{delay} 秒后重试",
                )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
        self.callbacks.on_status("stopped", "已停止")

    async def _session(self) -> None:
        headers = {"Authorization": f"Bearer {self.config.token}"}
        async with connect(
            self.config.websocket_url,
            additional_headers=headers,
            proxy=None,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=20,
            max_size=8 * 1024 * 1024,
        ) as websocket:
            self._websocket = websocket
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "node_id": self.config.node_id,
                        "name": self.config.node_name,
                        "capabilities": CAPABILITIES,
                    },
                    ensure_ascii=False,
                )
            )
            self.callbacks.on_status("online", self.config.server_url)
            _emit(self.callbacks, "INFO", "已连接 Echo，等待电脑操作")
            async for raw in websocket:
                if self._stop_requested.is_set():
                    break
                await self._handle_raw(websocket, raw)
        self._websocket = None

    async def _handle_raw(self, websocket, raw) -> None:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        message_type = payload.get("type")
        if message_type == "hello_ack":
            _emit(self.callbacks, "INFO", f"服务端已确认节点 {self.config.node_id}")
            return
        if message_type == "pong":
            return
        if message_type != "command":
            return
        try:
            command = parse_command(payload)
        except ValueError:
            return
        _emit(self.callbacks, "INFO", f"收到操作请求：{command.action}")
        self.callbacks.on_action(command.action, "running", "")
        try:
            data = await self._execute(command)
        except ActionError as exc:
            await websocket.send(
                json.dumps(result_payload(command.command_id, error=exc), ensure_ascii=False)
            )
            self.callbacks.on_action(command.action, "failed", exc.code)
            _emit(self.callbacks, "WARN", f"操作未完成：{command.action} ({exc.code})")
        except Exception as exc:
            error = ActionError("action_failed", str(exc))
            await websocket.send(
                json.dumps(result_payload(command.command_id, error=error), ensure_ascii=False)
            )
            self.callbacks.on_action(command.action, "failed", type(exc).__name__)
            _emit(self.callbacks, "ERROR", f"操作异常：{command.action} ({type(exc).__name__})")
        else:
            await websocket.send(
                json.dumps(
                    result_payload(command.command_id, data=data),
                    ensure_ascii=False,
                )
            )
            self.callbacks.on_action(command.action, "completed", "")
            _emit(self.callbacks, "INFO", f"操作完成：{command.action}")

    async def _execute(self, command: Command) -> dict:
        if self.auto_approve:
            self.callbacks.on_action(command.action, "auto_approved", "")
            _emit(self.callbacks, "INFO", f"总是允许：{command.action}")
            return await execute_command(command, approval=_always_allow)
        return await execute_command(command, approval=default_approval)


async def run_node(config: DesktopConfig) -> None:
    runtime = NodeRuntime(config)

    async def _run() -> None:
        await runtime._run_forever()

    await _run()
