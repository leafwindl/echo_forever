from __future__ import annotations

from typing import Any

from features.desktop.application.desktop_service import DesktopNodeStatus
from features.desktop.application.manage_nodes import PairedNode, PairingCode
from features.desktop.domain.entities import (
    DesktopCommandResult,
    DesktopError,
    DesktopNode,
    DesktopOfflineError,
    DesktopPairingError,
    DesktopTimeoutError,
)
from features.desktop.infrastructure.container import (
    get_desktop_node_management,
    get_desktop_service,
)


def create_desktop_pairing_code(user_id: str) -> PairingCode:
    return get_desktop_node_management().create_pairing_code(user_id)


def pair_desktop_node(
    *,
    code: str,
    node_name: str,
    fingerprint: str,
    capabilities: tuple[str, ...],
) -> PairedNode:
    return get_desktop_node_management().pair_node(
        code=code,
        node_name=node_name,
        fingerprint=fingerprint,
        capabilities=capabilities,
    )


def list_desktop_nodes(user_id: str) -> list[DesktopNodeStatus]:
    return get_desktop_service().status(user_id)


def revoke_desktop_node(user_id: str, node_id: str) -> bool:
    return get_desktop_service().revoke_node(user_id, node_id)


def mark_desktop_node_online(node: DesktopNode) -> None:
    get_desktop_service().mark_online(node)


def mark_desktop_node_offline(node: DesktopNode) -> None:
    get_desktop_service().mark_offline(node)


def authenticate_desktop_node(token: str) -> DesktopNode | None:
    return get_desktop_service().management.authenticate_token(token)


async def execute_desktop_action(
    *,
    user_id: str,
    action: str,
    arguments: dict[str, Any],
    timeout_seconds: int | None = None,
) -> DesktopCommandResult:
    return await get_desktop_service().execute(
        user_id=user_id,
        action=action,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "DesktopError",
    "DesktopNode",
    "DesktopOfflineError",
    "DesktopPairingError",
    "DesktopTimeoutError",
    "PairingCode",
    "PairedNode",
    "authenticate_desktop_node",
    "create_desktop_pairing_code",
    "execute_desktop_action",
    "list_desktop_nodes",
    "pair_desktop_node",
    "revoke_desktop_node",
]
