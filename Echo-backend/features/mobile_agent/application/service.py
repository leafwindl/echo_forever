from __future__ import annotations

import time
import uuid
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
    MobileAgentError,
    MobileAgentTimeoutError,
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

    def list_actions(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self.management.repository.list_actions(user_id, limit)

    async def execute(
        self,
        *,
        user_id: str,
        device_id: str,
        action: str,
        arguments: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> MobileAgentCommandResult:
        action_id = f"maction_{uuid.uuid4().hex}"
        started = time.monotonic()
        self.management.repository.record_action_start(
            action_id=action_id,
            device_id=device_id,
            user_id=user_id,
            action=action,
        )
        try:
            result = await self.hub.execute(
                user_id=user_id,
                device_id=device_id,
                action=action,
                arguments=arguments,
                timeout_seconds=timeout_seconds or self.command_timeout_seconds,
            )
        except MobileAgentTimeoutError:
            self._finish_action(action_id, "timed_out", "mobile_agent_timeout", started)
            raise
        except MobileAgentError as exc:
            self._finish_action(action_id, "failed", exc.code, started)
            raise
        except Exception:
            self._finish_action(action_id, "failed", "mobile_agent_failed", started)
            raise
        self._finish_action(action_id, "completed", None, started)
        return result

    def _finish_action(
        self,
        action_id: str,
        status: str,
        error_code: str | None,
        started: float,
    ) -> None:
        self.management.repository.record_action_finish(
            action_id=action_id,
            status=status,
            error_code=error_code,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
