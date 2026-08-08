from __future__ import annotations

from features.push.domain.repositories import PushTargetWriter


class ManagePushTargets:
    def __init__(self, repository: PushTargetWriter):
        self.repository = repository

    def register(
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
    ) -> None:
        self.repository.register_target(
            user_id=user_id,
            device_id=device_id,
            platform=platform,
            provider=provider,
            token=token,
            app_version=app_version,
            environment=environment,
            locale=locale,
        )

    def unregister(self, *, user_id: str, device_id: str) -> None:
        self.repository.revoke_target(user_id=user_id, device_id=device_id)
