from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from features.mobile_agent.domain.entities import (
    MobileAgentCommandResult,
    MobileAgentDevice,
    MobileAgentError,
    MobileAgentOfflineError,
    MobileAgentPairingError,
    MobileAgentTimeoutError,
)
from features.mobile_agent.infrastructure.container import (
    get_mobile_agent_hub,
    get_mobile_agent_service,
)


@dataclass(frozen=True)
class MobileAgentDeviceStatus:
    device: MobileAgentDevice
    online: bool


def list_mobile_agent_devices(user_id: str) -> list[MobileAgentDeviceStatus]:
    service = get_mobile_agent_service()
    hub = get_mobile_agent_hub()
    return [
        MobileAgentDeviceStatus(device=device, online=hub.is_online(device.device_id))
        for device in service.list_devices(user_id)
    ]


async def execute_mobile_agent_action(
    *,
    user_id: str,
    device_id: str,
    action: str,
    arguments: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
) -> MobileAgentCommandResult:
    return await get_mobile_agent_service().execute(
        user_id=user_id,
        device_id=device_id,
        action=action,
        arguments=arguments or {},
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "MobileAgentDeviceStatus",
    "MobileAgentError",
    "MobileAgentOfflineError",
    "MobileAgentPairingError",
    "MobileAgentTimeoutError",
    "execute_mobile_agent_action",
    "list_mobile_agent_devices",
]
