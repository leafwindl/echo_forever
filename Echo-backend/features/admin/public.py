from features.admin.application.debug_admin import AdminValidationError
from features.admin.domain.entities import ChatContextClearResult, RuntimePrompt
from features.admin.infrastructure.container import (
    get_clear_chat_context_use_case,
    get_runtime_prompt_use_case,
)


def get_effective_system_prompt() -> RuntimePrompt:
    use_case = get_runtime_prompt_use_case()
    return use_case.get_system_prompt()


def update_runtime_system_prompt(prompt: str) -> RuntimePrompt:
    use_case = get_runtime_prompt_use_case()
    return use_case.update_system_prompt(prompt)


def clear_user_chat_context(user_id: str) -> ChatContextClearResult:
    use_case = get_clear_chat_context_use_case()
    return use_case.execute(user_id)


__all__ = [
    "AdminValidationError",
    "ChatContextClearResult",
    "RuntimePrompt",
    "clear_user_chat_context",
    "get_effective_system_prompt",
    "update_runtime_system_prompt",
]
