from dataclasses import dataclass, field
from typing import Dict, List


class ChatValidationError(ValueError):
    """Raised when a chat use case receives invalid input."""


@dataclass(frozen=True)
class ChatContext:
    messages: List[Dict[str, str]]
    history_messages: List[Dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: List[Dict[str, object]] = field(default_factory=list)
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
