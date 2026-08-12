from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from features.agent.domain.entities import ContentPart, SourceReference

CONVERSATION_MODES = ("chat", "call")


class ChatValidationError(ValueError):
    """Raised when a chat use case receives invalid input."""


class ChatRequestInProgressError(RuntimeError):
    """Raised when the same user already has a chat request in progress."""


class ChatQueueFullError(RuntimeError):
    """Raised when a conversation has too many messages waiting for Echo."""


class ChatRequestClaimStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    CONFLICT = "conflict"


class ChatTurnStatus(StrEnum):
    COLLECTING = "collecting"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ChatContext:
    messages: list[dict[str, str]]
    history_messages: list[dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: list[dict[str, object]] = field(default_factory=list)
    memory_retrieval_mode: str = "none"
    pause_followup_questions: bool = False
    allow_proactive_stickers: bool = True
    proactive_sticker_due: bool = False


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
    reply_segments: tuple[str, ...] = ()
    sticker_placement: str = "after_text"


@dataclass(frozen=True)
class PreparedChatReply:
    reply: str
    reply_segments: tuple[str, ...]
    sources: tuple[SourceReference, ...] = ()
    content_parts: tuple[ContentPart, ...] = ()
    sticker_placement: str = "after_text"
    run_id: str = ""
    error_code: str | None = None


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
    stable_message_id: str = ""
    client_message_id: str = ""
    agent_turn_id: str = ""
    reply_group_id: str = ""
    sequence_in_group: int = 0
    in_reply_to_message_id: int | None = None
    sources: tuple[SourceReference, ...] = ()


@dataclass(frozen=True)
class ChatHistoryPage:
    conversation_id: str
    items: tuple[ChatHistoryMessage, ...]
    has_more: bool
    next_before_id: int | None = None
    next_after_id: int | None = None


@dataclass(frozen=True)
class ExternalAssistantDelivery:
    conversation_id: str
    message: ChatHistoryMessage
    replayed: bool = False


@dataclass(frozen=True)
class ChatAcceptedTurn:
    turn_id: str
    status: ChatTurnStatus


@dataclass(frozen=True)
class ChatMessageAcceptance:
    conversation_id: str
    message: ChatHistoryMessage
    turn: ChatAcceptedTurn
    replayed: bool = False


@dataclass(frozen=True)
class ChatTurnJob:
    turn_id: str
    user_id: str
    conversation_id: str
    status: ChatTurnStatus
    input_first_message_id: int
    input_last_message_id: int
    message_count: int
    character_count: int
    attempt_count: int
    max_attempts: int
    started_at: datetime | None = None


@dataclass(frozen=True)
class ChatBatchInput:
    turn: ChatTurnJob
    messages: tuple[ChatHistoryMessage, ...]
    combined_content: str
    sticker_intent: str = ""


@dataclass(frozen=True)
class ChatDeliveryPresentation:
    agent_elapsed_ms: int
    initial_delay_ms: int
    message_delays_ms: tuple[int, ...]


@dataclass(frozen=True)
class ChatReplyGroup:
    turn_id: str
    reply_group_id: str
    conversation_id: str
    messages: tuple[ChatHistoryMessage, ...]
    presentation: ChatDeliveryPresentation
