from datetime import date, datetime, time
from typing import Protocol

from features.letters.domain.entities import DailyLetter, LetterPreference


class LetterRepository(Protocol):
    def get_preference(self, user_id: str) -> LetterPreference: ...
    def save_preference(
        self, user_id: str, enabled: bool, timezone_name: str, publish_time: time
    ) -> LetterPreference: ...
    def list_letters(self, user_id: str, limit: int = 20) -> list[DailyLetter]: ...
    def due_users(self, now_utc: datetime) -> list[tuple[str, LetterPreference, date]]: ...
    def source_messages(
        self, user_id: str, local_date: date, timezone_name: str
    ) -> list[dict]: ...
    def exists(self, user_id: str, local_date: date) -> bool: ...
    def create_ready(
        self,
        user_id: str,
        local_date: date,
        timezone_name: str,
        subject: str,
        content: str,
        source_ids: list[int],
    ) -> bool: ...
    def create_skipped(self, user_id: str, local_date: date, timezone_name: str) -> None: ...
