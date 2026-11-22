from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


async def relay_wechat_message(
    *,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    image_base64: str = "",
    image_hash: str = "",
) -> None:
    """微信桥事件入口：Echo 回复后把结果发回微信。"""
    image_description = ""
    if image_base64:
        # 视觉识别放在 feature 入口层，application 只接收识别结果
        try:
            from providers.vision_provider import describe_desktop_image

            image_description = await describe_desktop_image(
                image_base64=image_base64,
                mime_type="image/png",
                question="这是微信聊天里收到的一张图片，请用中文简短描述图片内容。",
            )
        except Exception:
            logger.warning("wechat image vision failed", exc_info=True)

    # 延迟导入：wechat_events 依赖 chat.public，而 chat 侧也可能导入 desktop
    from features.desktop.application.wechat_events import handle_wechat_message

    await handle_wechat_message(
        service=get_desktop_service(),
        user_id=user_id,
        chat=chat,
        content=content,
        local_id=local_id,
        image_base64=image_base64,
        image_hash=image_hash,
        image_description=image_description,
    )


async def send_wechat_message(*, user_id: str, chat: str, text: str) -> bool:
    """主动消息投递到微信（Echo 自己的电脑）。"""
    from features.desktop.application.wechat_events import send_wechat_text

    return await send_wechat_text(
        service=get_desktop_service(),
        user_id=user_id,
        chat=chat,
        text=text,
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
    "create_echo_computer",
    "execute_desktop_action",
    "list_desktop_nodes",
    "pair_desktop_node",
    "revoke_desktop_node",
]
