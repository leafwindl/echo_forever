from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from features.desktop.domain.entities import DesktopNode, DesktopPairingError
from features.desktop.domain.repositories import DesktopRepository
from features.desktop.domain.rules import (
    generate_node_token,
    generate_pairing_code,
    node_token_hash,
    pairing_code_hash,
)


@dataclass(frozen=True)
class PairingCode:
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class PairedNode:
    node: DesktopNode
    token: str


class DesktopNodeManagement:
    def __init__(
        self,
        repository: DesktopRepository,
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
                code_hash=pairing_code_hash(code, self.pairing_secret),
                user_id=user_id,
                expires_at=expires_at,
            ):
                return PairingCode(code=code, expires_at=expires_at)
        raise RuntimeError("Could not allocate a unique desktop pairing code")

    def pair_node(
        self,
        *,
        code: str,
        node_name: str,
        fingerprint: str,
        capabilities: tuple[str, ...],
    ) -> PairedNode:
        token = generate_node_token()
        node = self.repository.pair_node(
            code_hash=pairing_code_hash(code, self.pairing_secret),
            node_name=node_name.strip()[:80] or "我的电脑",
            fingerprint=fingerprint.strip()[:128],
            token_hash=node_token_hash(token),
            node_id=f"dnode_{uuid.uuid4().hex}",
            capabilities=capabilities,
            now=datetime.now(UTC),
        )
        if node is None:
            raise DesktopPairingError()
        return PairedNode(node=node, token=token)

    def list_nodes(self, user_id: str) -> list[DesktopNode]:
        return self.repository.list_nodes(user_id)

    def revoke_node(self, user_id: str, node_id: str) -> bool:
        return self.repository.revoke_node(user_id, node_id)

    def authenticate_token(self, token: str) -> DesktopNode | None:
        if not token.strip():
            return None
        return self.repository.find_node_by_token_hash(node_token_hash(token))
