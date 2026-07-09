from typing import Optional

from features.admin.application.debug_admin import ClearUserChatContext, ManageRuntimePrompt
from features.admin.infrastructure.adapters import (
    SQLiteChatContextAdminRepository,
    SQLiteRuntimeSettingsRepository,
)
from shared.config import settings

_runtime_prompt_use_case: Optional[ManageRuntimePrompt] = None
_clear_chat_context_use_case: Optional[ClearUserChatContext] = None


def get_runtime_prompt_use_case() -> ManageRuntimePrompt:
    global _runtime_prompt_use_case
    if _runtime_prompt_use_case is None:
        _runtime_prompt_use_case = ManageRuntimePrompt(
            runtime_settings=SQLiteRuntimeSettingsRepository(),
            default_system_prompt=settings.system_prompt,
        )
    return _runtime_prompt_use_case


def get_clear_chat_context_use_case() -> ClearUserChatContext:
    global _clear_chat_context_use_case
    if _clear_chat_context_use_case is None:
        _clear_chat_context_use_case = ClearUserChatContext(
            chat_context_repository=SQLiteChatContextAdminRepository(),
        )
    return _clear_chat_context_use_case


def reset_admin_use_cases_for_tests():
    global _runtime_prompt_use_case, _clear_chat_context_use_case
    _runtime_prompt_use_case = None
    _clear_chat_context_use_case = None
