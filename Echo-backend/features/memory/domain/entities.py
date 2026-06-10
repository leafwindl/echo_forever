from dataclasses import dataclass
from typing import Optional

MEMORY_EXTRACTION_JOB_TYPE = "memory_extraction"
VALID_MEMORY_STATUSES = frozenset({"active", "inactive", "deleted"})


class MemoryValidationError(ValueError):
    """公开记忆输入违反领域规则时抛出。"""

    pass


class InvalidMemoryStatusError(MemoryValidationError):
    """状态过滤条件不属于支持范围时抛出。"""

    pass


class MemoryNotFoundError(LookupError):
    """用户操作不存在或不属于自己的记忆时抛出。"""

    pass


class MemoryOperationError(RuntimeError):
    """持久化层返回非预期记忆操作失败时抛出。"""

    pass


@dataclass(frozen=True)
class MemoryImportance:
    """有边界的重要性分数，用于提示词排序和降级召回。"""

    value: int

    def __post_init__(self):
        """限制重要性范围，避免模型输出破坏排序规则。"""
        if self.value < 1 or self.value > 5:
            raise ValueError("Memory importance must be between 1 and 5")


@dataclass(frozen=True)
class Memory:
    """一条用户长期记忆的纯领域对象。"""

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
    """有限记忆列表读取的应用层结果。"""

    memories: list[Memory]
    count: int


@dataclass(frozen=True)
class MemoryDeleteResult:
    """面向用户删除记忆的应用层结果。"""

    memory_id: str
    status: str


@dataclass(frozen=True)
class MemoryClearResult:
    """清空用户记忆的应用层结果。"""

    cleared_count: int


@dataclass(frozen=True)
class MemoryBackfillResult:
    """向量补齐任务的应用层结果。"""

    backfilled_count: int


@dataclass(frozen=True)
class MemoryGateResult:
    """用于判断一轮对话是否需要变成抽取任务的门控结果。"""

    should_extract: bool
    reason: str
    job_id: str = ""


@dataclass
class MemoryExtractionResult:
    """单个记忆抽取任务的持久化结果统计。"""

    created: int = 0
    updated: int = 0
    deactivated: int = 0
    ignored: int = 0


@dataclass(frozen=True)
class MemoryExtractionConfig:
    """由基础设施注入的运行参数，避免应用层直接读取配置。"""

    model: str
    temperature: float
    max_tokens: int
    max_existing_memories: int = 30
    max_resumed_jobs: int = 20
