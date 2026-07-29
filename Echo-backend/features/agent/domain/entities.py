from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolRisk(StrEnum):
    READ = "read"
    CREATE_INTERNAL = "create_internal"
    SEND = "send"
    DESTRUCTIVE = "destructive"


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
class AgentEnrichment:
    system_messages: tuple[dict[str, str], ...] = field(default_factory=tuple)
    sources: tuple[SourceReference, ...] = field(default_factory=tuple)
    content_parts: tuple[ContentPart, ...] = field(default_factory=tuple)
    run_id: str = ""


@dataclass(frozen=True)
class ToolSpecification:
    name: str
    description: str
    risk_level: ToolRisk
    timeout_seconds: int
    is_idempotent: bool = True


@dataclass(frozen=True)
class ToolResult:
    content: dict[str, Any]
    safe_for_prompt: str

