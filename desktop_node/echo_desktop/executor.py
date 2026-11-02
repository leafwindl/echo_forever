from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from echo_desktop.actions.apps import APP_LABELS, launch_app
from echo_desktop.actions.capture import capture_camera, capture_screen
from echo_desktop.actions.media import send_media_key
from echo_desktop.approvals import ask_windows_approval
from echo_desktop.protocol import ActionError, Command

Approval = Callable[..., Awaitable[bool]]

_MEDIA_LABELS = {
    "play_pause": "播放/暂停",
    "next": "下一首",
    "previous": "上一首",
}
_APPROVAL_MESSAGES = {
    "open_app": "Echo 想在你的电脑上打开：{app}。\n允许这一次吗？",
    "media_control": "Echo 想控制网易云音乐：{action}。\n允许这一次吗？",
    "screen_capture": "Echo 想截取当前屏幕看一眼。\n允许这一次吗？",
    "camera_capture": "Echo 想打开摄像头看一眼，不会持续录制。\n允许这一次吗？",
}


async def default_approval(title: str, message: str, *, warning: bool = False) -> bool:
    return await asyncio.to_thread(
        ask_windows_approval,
        title,
        message,
        warning=warning,
    )


def _approval_text(command: Command) -> str:
    if command.action == "open_app":
        app = str(command.arguments.get("app") or "")
        return _APPROVAL_MESSAGES["open_app"].format(app=APP_LABELS.get(app, app))
    if command.action == "media_control":
        action = str(command.arguments.get("action") or "")
        return _APPROVAL_MESSAGES["media_control"].format(
            action=_MEDIA_LABELS.get(action, action)
        )
    template = _APPROVAL_MESSAGES.get(command.action)
    if template is None:
        raise ActionError("unsupported_action", "这个电脑操作还没有实现。")
    return template


def _execute_action(command: Command) -> dict[str, Any]:
    if command.action == "open_app":
        app = str(command.arguments.get("app") or "")
        return launch_app(app)
    if command.action == "media_control":
        return send_media_key(str(command.arguments.get("action") or ""))
    if command.action == "screen_capture":
        return capture_screen()
    if command.action == "camera_capture":
        return capture_camera()
    raise ActionError("unsupported_action", "这个电脑操作还没有实现。")


async def execute_command(
    command: Command,
    *,
    approval: Approval = default_approval,
) -> dict[str, Any]:
    text = _approval_text(command)
    warning = command.action in {"camera_capture", "screen_capture"}
    approved = await approval("Echo Desktop", text, warning=warning)
    if not approved:
        raise ActionError("user_denied", "用户拒绝了这次电脑操作。")
    return await asyncio.to_thread(_execute_action, command)
