from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from features.mobile_agent.domain.entities import (
    MobileAgentDevice,
    MobileAgentPairingError,
)
from features.mobile_agent.domain.repositories import MobileAgentRepository
from features.mobile_agent.domain.rules import (
    generate_device_token,
    generate_pairing_code,
    hash_secret,
    normalize_device_name,
)


@dataclass(frozen=True)
class PairingCode:
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class PairedDevice:
    device: MobileAgentDevice
    token: str


class MobileAgentManagement:
    def __init__(
        self,
        *,
        repository: MobileAgentRepository,
        pairing_secret: str,
        pairing_code_ttl_seconds: int,
    ):
        self.repository = repository
        self.pairing_secret = pairing_secret
        self.pairing_code_ttl_seconds = pairing_code_ttl_seconds

    def create_pairing_code(self, user_id: str) -> PairingCode:
        for _ in range(5):
            code = generate_pairing_code()
            expires_at = datetime.now(UTC) + timedelta(
                seconds=self.pairing_code_ttl_seconds
            )
            if self.repository.create_pairing_code(
                code_hash=hash_secret(code, self.pairing_secret),
                user_id=user_id,
                expires_at=expires_at,
            ):
                return PairingCode(code=code, expires_at=expires_at)
        raise RuntimeError("Could not allocate a unique mobile agent pairing code")

    def pair_device(self, *, code: str, device_name: str) -> PairedDevice:
        token = generate_device_token()
        device = self.repository.pair_device(
            code_hash=hash_secret(code.strip().upper(), self.pairing_secret),
            device_name=normalize_device_name(device_name),
            token_hash=hash_secret(token, self.pairing_secret),
            device_id=f"mdev_{uuid.uuid4().hex}",
            now=datetime.now(UTC),
        )
        if device is None:
            raise MobileAgentPairingError()
        return PairedDevice(device=device, token=token)

    def authenticate(self, token: str) -> MobileAgentDevice | None:
        if not token.strip():
            return None
        return self.repository.find_by_token_hash(
            hash_secret(token, self.pairing_secret)
        )

    def list_devices(self, user_id: str) -> list[MobileAgentDevice]:
        return self.repository.list_devices(user_id)

    def revoke(self, user_id: str, device_id: str) -> bool:
        return self.repository.revoke_device(user_id, device_id)

    def mark_online(self, device_id: str) -> None:
        self.repository.mark_online(device_id)

    def mark_offline(self, device_id: str) -> None:
        self.repository.mark_offline(device_id)
