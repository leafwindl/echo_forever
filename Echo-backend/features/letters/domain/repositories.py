from datetime import date, datetime, time
from typing import Any, Protocol

from features.letters.domain.entities import DailyLetter, LetterGenerationTask, LetterPreference


class LetterRepository(Protocol):
    def get_preference(self, user_id: str) -> LetterPreference: ...
    def save_preference(
        self, user_id: str, enabled: bool, timezone_name: str, publish_time: time
    ) -> LetterPreference: ...
    def list_letters(self, user_id: str, limit: int = 20) -> list[DailyLetter]: ...
    def source_messages(
        self, user_id: str, local_date: date, timezone_name: str
    ) -> list[dict[str, Any]]: ...

    def ensure_due_generation_tasks(self, now_utc: datetime) -> int: ...

    def claim_generation_task(self, now_utc: datetime) -> LetterGenerationTask | None: ...

    def complete_generation(
        self,
        task: LetterGenerationTask,
        *,
        subject: str,
        content: str,
        reflection: str,
        mood: str,
        image_brief: dict,
        source_message_ids: list[int],
        source_memory_ids: list[str],
        agent_run_id: str = "",
        context_version: str = "",
        context_snapshot: dict[str, object] | None = None,
        image_storage_key: str = "",
        image_content_type: str = "",
        image_width: int | None = None,
        image_height: int | None = None,
        image_byte_size: int | None = None,
        image_provider: str = "",
        image_model: str = "",
        image_reference_version: str = "",
        image_status: str = "disabled",
        image_failure_code: str | None = None,
    ) -> bool: ...

    def create_skipped(self, task: LetterGenerationTask, reason: str) -> bool: ...

    def fail_generation(
        self,
        task: LetterGenerationTask,
        error_code: str,
        now_utc: datetime,
    ) -> None: ...

    def publish_due(self, now_utc: datetime) -> int: ...
