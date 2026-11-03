from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from features.mobile_agent.domain.entities import (
    MobileAgentActionError,
    MobileAgentCommandResult,
    MobileAgentDevice,
    MobileAgentOfflineError,
    MobileAgentTimeoutError,
)


class MobileAgentChannel(Protocol):
    device_id: str
    user_id: str

    async def send(self, payload: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


@dataclass
class _Connection:
    device: MobileAgentDevice
    channel: MobileAgentChannel
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MobileAgentHub:
    def __init__(self):
        self._connections: dict[str, _Connection] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def register(self, device: MobileAgentDevice, channel: MobileAgentChannel) -> None:
        self._connections[device.device_id] = _Connection(
            device=device,
            channel=channel,
        )

    def unregister(self, device: MobileAgentDevice) -> None:
        self._connections.pop(device.device_id, None)
        for command_id, future in list(self._pending.items()):
            if command_id.startswith(device.device_id + ":"):
                self._pending.pop(command_id, None)
                if not future.done():
                    future.set_exception(MobileAgentOfflineError())

    async def disconnect(self, device_id: str) -> None:
        connection = self._connections.pop(device_id, None)
        if connection is not None:
            with contextlib.suppress(Exception):
                await connection.channel.close()

    def is_online(self, device_id: str) -> bool:
        return device_id in self._connections

    def select(self, user_id: str, device_id: str) -> MobileAgentDevice:
        connection = self._connections.get(device_id)
        if connection is None or connection.device.user_id != user_id:
            raise MobileAgentOfflineError()
        return connection.device

    async def execute(
        self,
        *,
        user_id: str,
        device_id: str,
        action: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
    ) -> MobileAgentCommandResult:
        connection = self._connections.get(device_id)
        if connection is None or connection.device.user_id != user_id:
            raise MobileAgentOfflineError()
        command_id = f"{device_id}:{uuid.uuid4().hex}"
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[command_id] = future
        payload = {
            "type": "command",
            "command_id": command_id,
            "action": action,
            "arguments": arguments,
        }
        try:
            try:
                await connection.channel.send(payload)
            except Exception as exc:
                raise MobileAgentActionError(
                    "mobile_agent_send_failed",
                    "手机 Agent 连接异常，命令没有送达",
                ) from exc
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise MobileAgentTimeoutError() from exc
        finally:
            self._pending.pop(command_id, None)

        error = response.get("error")
        if error:
            code = str(error.get("code") or "mobile_agent_action_failed")
            message = str(error.get("message") or "")
            raise MobileAgentActionError(code, message)
        data = response.get("data")
        return MobileAgentCommandResult(
            command_id=command_id,
            device_id=device_id,
            data=data if isinstance(data, dict) else {},
        )

    def handle_message(self, device: MobileAgentDevice, payload: dict[str, Any]) -> None:
        message_type = str(payload.get("type") or "")
        if message_type == "result":
            command_id = str(payload.get("command_id") or "")
            future = self._pending.get(command_id)
            if future is not None and not future.done():
                future.set_result(payload)
            return
        if message_type == "ping":
            connection = self._connections.get(device.device_id)
            if connection is not None:
                asyncio.create_task(connection.channel.send({"type": "pong"}))
