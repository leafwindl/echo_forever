from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# 事件类型：消息、工具调用、主动发送、B站分享
EVENT_MESSAGE = "message"
EVENT_TOOL_CALL = "tool_call"
EVENT_SEND = "send"
EVENT_SHARE = "share"

# 谁产生的这条事件
ACTOR_USER = "user"
ACTOR_ECHO = "echo"
ACTOR_SYSTEM = "system"


@dataclass(frozen=True)
class ConversationEvent:
    event_type: str
    source: str
    actor: str
    user_id: str
    conversation_id: str | None = None
    turn_id: str = ""
    content: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    source_created_at: datetime | None = None


__all__ = [
    "ACTOR_ECHO",
    "ACTOR_SYSTEM",
    "ACTOR_USER",
    "EVENT_MESSAGE",
    "EVENT_SEND",
    "EVENT_SHARE",
    "EVENT_TOOL_CALL",
    "ConversationEvent",
]
