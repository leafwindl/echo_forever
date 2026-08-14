from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolRisk(StrEnum):
    READ = "read"
    CREATE_INTERNAL = "create_internal"
    SEND = "send"
    DESTRUCTIVE = "destructive"


class AgentToolStatus(StrEnum):
    COMPLETED = "completed"
    NO_RESULT = "no_result"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ProactiveAction(StrEnum):
    SEND = "send"
    SKIP = "skip"


@dataclass(frozen=True)
class ProactiveDecision:
    action: ProactiveAction
    topic: str = "casual_check_in"
    tone: str = "gentle"
    safe_fact_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""


@dataclass(frozen=True)
class SourceReference:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None


@dataclass(frozen=True)
class ContentPart:
    type: str
    text: str = ""
    sticker_id: str = ""
    url: str = ""


@dataclass(frozen=True)
class AgentToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentToolResult:
    call_id: str
    tool_name: str
    status: AgentToolStatus
    arguments: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    safe_for_model: str = ""
    content_parts: tuple[ContentPart, ...] = field(default_factory=tuple)
    sources: tuple[SourceReference, ...] = field(default_factory=tuple)
    error_code: str | None = None


@dataclass(frozen=True)
class AgentModelResponse:
    text: str = ""
    tool_calls: tuple[AgentToolCall, ...] = field(default_factory=tuple)
    finish_reason: str = ""
    provider_request_id: str = ""


@dataclass(frozen=True)
class AgentTurnResult:
    status: AgentRunStatus = AgentRunStatus.COMPLETED
    reply_text: str = ""
    sources: tuple[SourceReference, ...] = field(default_factory=tuple)
    content_parts: tuple[ContentPart, ...] = field(default_factory=tuple)
    tool_results: tuple[AgentToolResult, ...] = field(default_factory=tuple)
    run_id: str = ""
    model_steps: int = 0
    error_code: str | None = None
    reply_segments: tuple[str, ...] = field(default_factory=tuple)
    sticker_placement: str = "after_text"


@dataclass(frozen=True)
class ToolSpecification:
    name: str
    description: str
    risk_level: ToolRisk
    timeout_seconds: int
    is_idempotent: bool = True
    allowed_modes: tuple[str, ...] = ("chat", "call")
    max_calls_per_turn: int = 4
    max_successful_calls_per_turn: int | None = None
    count_no_result_toward_call_limit: bool = True
    allow_proactive: bool = False
