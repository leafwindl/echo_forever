from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

MOBILE_AGENT_CAPABILITIES: tuple[str, ...] = (
    "observe",
    "action",
    "launch_app",
)


@dataclass(frozen=True)
class MobileAgentDevice:
    device_id: str
    user_id: str
    name: str
    status: str = "offline"
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class MobileAgentCommandResult:
    command_id: str
    device_id: str
    data: dict[str, Any]


class MobileAgentError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class MobileAgentPairingError(MobileAgentError):
    def __init__(self):
        super().__init__("invalid_pairing_code", "配对码无效或已过期")


class MobileAgentOfflineError(MobileAgentError):
    def __init__(self):
        super().__init__("mobile_agent_offline", "手机 Agent 当前不在线")


class MobileAgentTimeoutError(MobileAgentError):
    def __init__(self):
        super().__init__("mobile_agent_timeout", "手机操作没有及时完成")


class MobileAgentActionError(MobileAgentError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(code, message)
