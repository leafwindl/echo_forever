from typing import Protocol


class RuntimeSettingsRepository(Protocol):
    def get_value(self, key: str) -> str | None:
        ...

    def set_value(self, key: str, value: str) -> None:
        ...


class ChatContextAdminRepository(Protocol):
    def clear_user_chat_context(self, user_id: str) -> tuple[int, int]:
        ...
