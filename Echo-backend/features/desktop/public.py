from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from features.desktop.application.desktop_service import DesktopNodeStatus
from features.desktop.application.manage_nodes import PairedNode, PairingCode
from features.desktop.application.remote_command import (
    RemoteCommandResult,
    run_remote_command,
)
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

logger = logging.getLogger(__name__)


async def relay_wechat_message(
    *,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    images: tuple[str, ...] = (),
    source_created_at: datetime | None = None,
) -> None:
    """微信桥事件入口：Echo 回复后把结果发回微信。"""
    # 延迟导入：wechat_events 依赖 chat.public，而 chat 侧也可能导入 desktop
    from features.desktop.application.wechat_events import handle_wechat_message

    await handle_wechat_message(
        service=get_desktop_service(),
        user_id=user_id,
        chat=chat,
        content=content,
        local_id=local_id,
        images=images,
        source_created_at=source_created_at,
    )


def start_bili_scan(
    *,
    user_id: str,
    conversation_id: str,
    item_limit: int = 8,
    source: str = "chat",
) -> dict[str, Any]:
    """发起一次异步B站扫描；同一用户已有任务时直接复用。"""
    from features.desktop.infrastructure.bili_scan_store import create_or_get_scan_job

    return create_or_get_scan_job(
        user_id=user_id,
        conversation_id=conversation_id,
        item_limit=item_limit,
        source=source,
    )


def recent_bili_scan_summaries(user_id: str, limit: int = 3) -> list[dict]:
    """最近完成的B站扫描摘要，供 presence 念头参考。"""
    from features.desktop.infrastructure.bili_scan_store import (
        recent_completed_scan_summaries,
    )

    return recent_completed_scan_summaries(user_id, limit)


async def send_wechat_message(*, user_id: str, chat: str, text: str) -> bool:
    """主动消息投递到微信（Echo 自己的电脑）。"""
    from features.desktop.application.wechat_events import send_wechat_text

    return await send_wechat_text(
        service=get_desktop_service(),
        user_id=user_id,
        chat=chat,
        text=text,
    )


async def send_wechat_delivery(*, user_id: str, items: tuple) -> bool:
    """主动消息投递微信：文字与表情包按交付顺序一次发出。"""
    from features.desktop.application.wechat_events import (
        send_wechat_delivery as _send_wechat_delivery,
    )

    return await _send_wechat_delivery(
        service=get_desktop_service(),
        user_id=user_id,
        items=items,
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


def list_desktop_nodes(user_id: str, owner_type: str | None = None) -> list[DesktopNodeStatus]:
    return get_desktop_service().status(user_id, owner_type)


def create_echo_computer(
    *,
    user_id: str,
    node_name: str,
    capabilities: tuple[str, ...],
) -> PairedNode:
    return get_desktop_node_management().create_echo_computer(
        user_id=user_id,
        node_name=node_name,
        capabilities=capabilities,
    )


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
    owner_type: str = "user",
) -> DesktopCommandResult:
    return await get_desktop_service().execute(
        user_id=user_id,
        action=action,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
        owner_type=owner_type,
    )


async def run_desktop_command(
    *,
    user_id: str,
    command: str,
    owner_type: str = "echo",
    timeout_seconds: int = 120,
    submit_timeout_seconds: int = 30,
    poll_interval_seconds: float = 2.0,
    poll_timeout_seconds: int = 20,
) -> RemoteCommandResult:
    """在电脑节点执行命令并等结果（异步 job 会自动轮询）。"""
    return await run_remote_command(
        get_desktop_service(),
        user_id=user_id,
        command=command,
        owner_type=owner_type,
        timeout_seconds=timeout_seconds,
        submit_timeout_seconds=submit_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        poll_timeout_seconds=poll_timeout_seconds,
    )


__all__ = [
    "DesktopError",
    "DesktopNode",
    "DesktopOfflineError",
    "DesktopPairingError",
    "DesktopTimeoutError",
    "PairingCode",
    "PairedNode",
    "RemoteCommandResult",
    "authenticate_desktop_node",
    "create_desktop_pairing_code",
    "create_echo_computer",
    "execute_desktop_action",
    "list_desktop_nodes",
    "pair_desktop_node",
    "revoke_desktop_node",
    "run_desktop_command",
    "recent_bili_scan_summaries",
    "send_wechat_delivery",
    "start_bili_scan",
]
