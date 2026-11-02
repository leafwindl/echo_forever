from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from features.desktop.domain.entities import (
    DesktopActionError,
    DesktopCommandResult,
    DesktopNode,
    DesktopOfflineError,
    DesktopTimeoutError,
)


class DesktopNodeChannel(Protocol):
    node_id: str
    user_id: str
    capabilities: tuple[str, ...]

    async def send(self, payload: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


@dataclass
class _Connection:
    node: DesktopNode
    channel: DesktopNodeChannel
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DesktopNodeHub:
    def __init__(self):
        self._connections: dict[str, _Connection] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def register(self, node: DesktopNode, channel: DesktopNodeChannel) -> None:
        self._connections[node.user_id + ":" + node.node_id] = _Connection(
            node=node,
            channel=channel,
        )

    def unregister(self, node: DesktopNode) -> None:
        key = node.user_id + ":" + node.node_id
        connection = self._connections.pop(key, None)
        if connection is None:
            return
        for command_id, future in list(self._pending.items()):
            if command_id.startswith(node.node_id + ":"):
                self._pending.pop(command_id, None)
                if not future.done():
                    future.set_exception(DesktopOfflineError())

    async def disconnect_node(self, node_id: str) -> None:
        for key, connection in list(self._connections.items()):
            if connection.node.node_id != node_id:
                continue
            self._connections.pop(key, None)
            with contextlib.suppress(Exception):
                await connection.channel.close()

    def is_online(self, user_id: str, node_id: str | None = None) -> bool:
        return any(
            key.startswith(user_id + ":")
            and (node_id is None or key.endswith(":" + node_id))
            for key in self._connections
        )

    def online_node_ids(self, user_id: str) -> tuple[str, ...]:
        return tuple(
            key.split(":", 1)[1]
            for key in self._connections
            if key.startswith(user_id + ":")
        )

    def select_node(self, user_id: str, node_id: str | None = None) -> DesktopNode:
        return self._select(user_id, node_id).node

    def _select(self, user_id: str, node_id: str | None = None) -> _Connection:
        candidates = [
            connection
            for key, connection in self._connections.items()
            if key.startswith(user_id + ":")
            and (node_id is None or connection.node.node_id == node_id)
        ]
        if not candidates:
            raise DesktopOfflineError()
        return max(candidates, key=lambda connection: connection.connected_at)

    async def execute(
        self,
        *,
        user_id: str,
        action: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        node_id: str | None = None,
    ) -> DesktopCommandResult:
        connection = self._select(user_id, node_id)
        command_id = f"{connection.node.node_id}:{uuid.uuid4().hex}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[command_id] = future
        payload = {
            "type": "command",
            "command_id": command_id,
            "action": action,
            "arguments": arguments,
            "timeout_seconds": timeout_seconds,
        }
        try:
            try:
                await connection.channel.send(payload)
            except Exception as exc:
                raise DesktopActionError(
                    "desktop_send_failed",
                    "电脑节点连接异常，操作没有送达。",
                ) from exc
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise DesktopTimeoutError() from exc
        finally:
            self._pending.pop(command_id, None)

        error = response.get("error")
        if error:
            code = str(error.get("code") or "desktop_action_failed")
            message = str(error.get("message") or "")
            raise DesktopActionError(code, message)
        data = response.get("data")
        return DesktopCommandResult(
            command_id=command_id,
            node_id=connection.node.node_id,
            data=data if isinstance(data, dict) else {},
        )

    def handle_message(self, node: DesktopNode, payload: dict[str, Any]) -> None:
        message_type = str(payload.get("type") or "")
        if message_type == "result":
            command_id = str(payload.get("command_id") or "")
            future = self._pending.get(command_id)
            if future is not None and not future.done():
                future.set_result(payload)
            return
        if message_type == "ping":
            connection = self._connections.get(node.user_id + ":" + node.node_id)
            if connection is not None:
                asyncio.create_task(connection.channel.send({"type": "pong"}))
