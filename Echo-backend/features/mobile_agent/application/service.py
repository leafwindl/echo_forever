from __future__ import annotations

from typing import Any

from features.mobile_agent.application.hub import MobileAgentHub
from features.mobile_agent.application.management import (
    MobileAgentManagement,
    PairedDevice,
    PairingCode,
)
from features.mobile_agent.domain.entities import (
    MobileAgentCommandResult,
    MobileAgentDevice,
)


class MobileAgentService:
    def __init__(
        self,
        *,
        management: MobileAgentManagement,
        hub: MobileAgentHub,
        command_timeout_seconds: int,
    ):
        self.management = management
        self.hub = hub
        self.command_timeout_seconds = command_timeout_seconds

    def create_pairing_code(self, user_id: str) -> PairingCode:
        return self.management.create_pairing_code(user_id)

    def pair_device(self, *, code: str, device_name: str) -> PairedDevice:
        return self.management.pair_device(code=code, device_name=device_name)

    def authenticate(self, token: str) -> MobileAgentDevice | None:
        return self.management.authenticate(token)

    def list_devices(self, user_id: str) -> list[MobileAgentDevice]:
        return self.management.list_devices(user_id)

    def mark_online(self, device_id: str) -> None:
        self.management.mark_online(device_id)

    def mark_offline(self, device_id: str) -> None:
        self.management.mark_offline(device_id)

    def revoke(self, user_id: str, device_id: str) -> bool:
        return self.management.revoke(user_id, device_id)

    async def execute(
        self,
        *,
        user_id: str,
        device_id: str,
        action: str,
        arguments: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> MobileAgentCommandResult:
        return await self.hub.execute(
            user_id=user_id,
            device_id=device_id,
            action=action,
            arguments=arguments,
            timeout_seconds=timeout_seconds or self.command_timeout_seconds,
        )
