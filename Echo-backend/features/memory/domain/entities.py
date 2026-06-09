from dataclasses import dataclass
from typing import Optional

MEMORY_EXTRACTION_JOB_TYPE = "memory_extraction"
VALID_MEMORY_STATUSES = frozenset({"active", "inactive", "deleted"})


class MemoryValidationError(ValueError):
    pass


class InvalidMemoryStatusError(MemoryValidationError):
    pass


class MemoryNotFoundError(LookupError):
    pass


class MemoryOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryImportance:
    value: int

    def __post_init__(self):
        if self.value < 1 or self.value > 5:
            raise ValueError("Memory importance must be between 1 and 5")


@dataclass(frozen=True)
class Memory:
    memory_id: str
    user_id: str
    memory_type: str
    content: str
    source_message_id: Optional[int]
    confidence: float
    importance: MemoryImportance
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass(frozen=True)
class MemoryListResult:
    memories: list[Memory]
    count: int


@dataclass(frozen=True)
class MemoryDeleteResult:
    memory_id: str
    status: str


@dataclass(frozen=True)
class MemoryClearResult:
    cleared_count: int


@dataclass(frozen=True)
class MemoryBackfillResult:
    backfilled_count: int


@dataclass(frozen=True)
class MemoryGateResult:
    """Gate result for deciding whether a chat turn should become an extraction job."""

    should_extract: bool
    reason: str
    job_id: str = ""


@dataclass
class MemoryExtractionResult:
    """Persistence result for one memory extraction job."""

    created: int = 0
    updated: int = 0
    deactivated: int = 0
    ignored: int = 0


@dataclass(frozen=True)
class MemoryExtractionConfig:
    model: str
    temperature: float
    max_tokens: int
    max_existing_memories: int = 30
    max_resumed_jobs: int = 20
