from __future__ import annotations

from datetime import datetime
from typing import Protocol

from features.desktop.domain.entities import DesktopNode


class DesktopRepository(Protocol):
    def create_pairing_code(
        self,
        *,
        code_hash: str,
        user_id: str,
        expires_at: datetime,
    ) -> bool: ...

    def pair_node(
        self,
        *,
        code_hash: str,
        node_name: str,
        fingerprint: str,
        token_hash: str,
        node_id: str,
        capabilities: tuple[str, ...],
        now: datetime,
    ) -> DesktopNode | None: ...

    def find_node_by_token_hash(self, token_hash: str) -> DesktopNode | None: ...

    def list_nodes(self, user_id: str) -> list[DesktopNode]: ...

    def revoke_node(self, user_id: str, node_id: str) -> bool: ...

    def mark_online(self, node_id: str, capabilities: tuple[str, ...]) -> None: ...

    def mark_offline(self, node_id: str) -> None: ...

    def record_action_start(
        self,
        *,
        action_id: str,
        node_id: str,
        user_id: str,
        action: str,
    ) -> None: ...

    def record_action_finish(
        self,
        *,
        action_id: str,
        status: str,
        error_code: str | None,
        duration_ms: int,
    ) -> None: ...
