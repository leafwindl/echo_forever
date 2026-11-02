from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from features.desktop.application.manage_nodes import DesktopNodeManagement
from features.desktop.application.node_hub import DesktopNodeHub
from features.desktop.domain.entities import (
    DesktopCommandResult,
    DesktopError,
    DesktopNode,
    DesktopOfflineError,
    DesktopTimeoutError,
)
from features.desktop.domain.repositories import DesktopRepository
from features.desktop.domain.rules import validate_action_arguments


@dataclass(frozen=True)
class DesktopNodeStatus:
    node: DesktopNode
    online: bool


class DesktopService:
    def __init__(
        self,
        repository: DesktopRepository,
        hub: DesktopNodeHub,
        management: DesktopNodeManagement,
        command_timeout_seconds: int,
    ):
        self.repository = repository
        self.hub = hub
        self.management = management
        self.command_timeout_seconds = command_timeout_seconds

    def mark_online(self, node: DesktopNode) -> None:
        self.repository.mark_online(node.node_id, node.capabilities)

    def mark_offline(self, node: DesktopNode) -> None:
        self.repository.mark_offline(node.node_id)

    def revoke_node(self, user_id: str, node_id: str) -> bool:
        return self.management.revoke_node(user_id, node_id)

    def status(self, user_id: str) -> list[DesktopNodeStatus]:
        online_ids = set(self.hub.online_node_ids(user_id))
        return [
            DesktopNodeStatus(node=node, online=node.node_id in online_ids)
            for node in self.repository.list_nodes(user_id)
        ]

    async def execute(
        self,
        *,
        user_id: str,
        action: str,
        arguments: dict[str, Any],
        timeout_seconds: int | None = None,
        node_id: str | None = None,
    ) -> DesktopCommandResult:
        cleaned = validate_action_arguments(action, arguments)
        timeout = timeout_seconds or self.command_timeout_seconds
        target = self.hub.select_node(user_id, node_id)
        action_id = f"dact_{uuid.uuid4().hex}"
        started = time.monotonic()
        self.repository.record_action_start(
            action_id=action_id,
            node_id=target.node_id,
            user_id=user_id,
            action=action,
        )
        try:
            result = await self.hub.execute(
                user_id=user_id,
                action=action,
                arguments=cleaned,
                timeout_seconds=timeout,
                node_id=target.node_id,
            )
        except DesktopOfflineError:
            self.repository.record_action_finish(
                action_id=action_id,
                status="failed",
                error_code="desktop_offline",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        except DesktopTimeoutError:
            self.repository.record_action_finish(
                action_id=action_id,
                status="timed_out",
                error_code="desktop_timeout",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        except DesktopError as exc:
            status = "denied" if exc.code == "user_denied" else "failed"
            self.repository.record_action_finish(
                action_id=action_id,
                status=status,
                error_code=exc.code,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        except Exception:
            self.repository.record_action_finish(
                action_id=action_id,
                status="failed",
                error_code="desktop_error",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        self.repository.record_action_finish(
            action_id=action_id,
            status="completed",
            error_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return result
