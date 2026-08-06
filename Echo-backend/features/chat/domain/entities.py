from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from features.agent.domain.entities import ContentPart, SourceReference

CONVERSATION_MODES = ("chat", "call")


class ChatValidationError(ValueError):
    """Raised when a chat use case receives invalid input."""


class ChatRequestInProgressError(RuntimeError):
    """Raised when the same user already has a chat request in progress."""


class ChatRequestClaimStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ChatContext:
    messages: list[dict[str, str]]
    history_messages: list[dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: list[dict[str, object]] = field(default_factory=list)
    memory_retrieval_mode: str = "none"
    pause_followup_questions: bool = False
    allow_proactive_stickers: bool = True


@dataclass(frozen=True)
class MemoryExtractionScheduleResult:
    should_extract: bool
    reason: str
    job_id: str = ""


@dataclass
class ChatTurnResult:
    reply: str
    user_message: str
    user_message_id: int
    assistant_message_id: int
    conversation_id: str
    summary_updated: bool = False
    memory_created: int = 0
    memory_updated: int = 0
    memory_deactivated: int = 0
    memory_extraction_scheduled: bool = False
    memory_extraction_gate_reason: str = ""
    memory_extraction_job_id: str = ""
    sources: tuple[SourceReference, ...] = ()
    content_parts: tuple[ContentPart, ...] = ()


@dataclass(frozen=True)
class ChatReplyDeliveryResult:
    reply: str
    audio_urls: tuple[str, ...] = ()
    sources: tuple[SourceReference, ...] = ()
    content_parts: tuple[ContentPart, ...] = ()


@dataclass(frozen=True)
class ChatRequestClaim:
    status: ChatRequestClaimStatus
    result: ChatReplyDeliveryResult | None = None


@dataclass(frozen=True)
class ChatContextClearResult:
    deleted_messages: int
    reset_conversations: int


@dataclass(frozen=True)
class ChatHistoryMessage:
    message_id: int
    role: str
    message_type: str
    content: str
    content_parts: tuple[ContentPart, ...]
    created_at: datetime


@dataclass(frozen=True)
class ChatHistoryPage:
    conversation_id: str
    items: tuple[ChatHistoryMessage, ...]
    has_more: bool
    next_before_id: int | None
