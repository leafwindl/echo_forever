from __future__ import annotations

from typing import Protocol


class PushTargetWriter(Protocol):
    def register_target(
        self,
        *,
        user_id: str,
        device_id: str,
        platform: str,
        provider: str,
        token: str,
        app_version: str,
        environment: str,
        locale: str,
    ) -> None: ...

    def revoke_target(self, *, user_id: str, device_id: str) -> None: ...
