from dataclasses import dataclass, field


class ChatValidationError(ValueError):
    """Raised when a chat use case receives invalid input."""


class ChatRequestInProgressError(RuntimeError):
    """Raised when the same user already has a chat request in progress."""


@dataclass(frozen=True)
class ChatContext:
    messages: list[dict[str, str]]
    history_messages: list[dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: list[dict[str, object]] = field(default_factory=list)
    memory_retrieval_mode: str = "none"


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


@dataclass(frozen=True)
class ChatReplyDeliveryResult:
    reply: str
    audio_urls: tuple[str, ...] = ()

    @property
    def audio_url(self) -> str | None:
        """Backward-compatible first audio segment URL."""
        return self.audio_urls[0] if self.audio_urls else None
