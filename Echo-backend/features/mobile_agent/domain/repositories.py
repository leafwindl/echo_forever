from __future__ import annotations

from datetime import datetime
from typing import Protocol

from features.mobile_agent.domain.entities import MobileAgentDevice


class MobileAgentRepository(Protocol):
    def create_pairing_code(
        self, *, code_hash: str, user_id: str, expires_at: datetime
    ) -> bool: ...

    def pair_device(
        self,
        *,
        code_hash: str,
        device_name: str,
        token_hash: str,
        device_id: str,
        now: datetime,
    ) -> MobileAgentDevice | None: ...

    def find_by_token_hash(self, token_hash: str) -> MobileAgentDevice | None: ...

    def list_devices(self, user_id: str) -> list[MobileAgentDevice]: ...

    def revoke_device(self, user_id: str, device_id: str) -> bool: ...

    def mark_online(self, device_id: str) -> None: ...

    def mark_offline(self, device_id: str) -> None: ...
