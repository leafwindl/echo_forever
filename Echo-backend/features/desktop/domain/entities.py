from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DESKTOP_CAPABILITIES: tuple[str, ...] = (
    "open_app",
    "media_control",
    "screen_capture",
    "camera_capture",
)

ALLOWED_APPS: tuple[str, ...] = (
    "netease_cloud_music",
    "notepad",
    "calculator",
)

MEDIA_ACTIONS: tuple[str, ...] = ("play_pause", "next", "previous")


@dataclass(frozen=True)
class DesktopNode:
    node_id: str
    user_id: str
    name: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    status: str = "offline"
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class DesktopCommandResult:
    command_id: str
    node_id: str
    data: dict[str, Any] = field(default_factory=dict)


class DesktopError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class DesktopOfflineError(DesktopError):
    def __init__(self):
        super().__init__("desktop_offline", "电脑上的 Echo Desktop 当前不在线")


class DesktopTimeoutError(DesktopError):
    def __init__(self):
        super().__init__("desktop_timeout", "电脑上的操作没有及时完成")


class DesktopActionError(DesktopError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(code, message)


class DesktopPairingError(DesktopError):
    def __init__(self):
        super().__init__("invalid_pairing_code", "配对码无效或已过期")
