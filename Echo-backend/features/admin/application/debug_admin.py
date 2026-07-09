from features.admin.domain.entities import (
    SYSTEM_PROMPT_SETTING_KEY,
    ChatContextClearResult,
    RuntimePrompt,
)
from features.admin.domain.services import ChatContextAdminRepository, RuntimeSettingsRepository


class AdminValidationError(ValueError):
    pass


class ManageRuntimePrompt:
    def __init__(self, runtime_settings: RuntimeSettingsRepository, default_system_prompt: str):
        self.runtime_settings = runtime_settings
        self.default_system_prompt = default_system_prompt

    def get_system_prompt(self) -> RuntimePrompt:
        runtime_prompt = self.runtime_settings.get_value(SYSTEM_PROMPT_SETTING_KEY)
        if runtime_prompt is not None:
            return RuntimePrompt(content=runtime_prompt, source="runtime_settings")
        return RuntimePrompt(content=self.default_system_prompt, source="env")

    def update_system_prompt(self, prompt: str) -> RuntimePrompt:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise AdminValidationError("System prompt cannot be empty")

        self.runtime_settings.set_value(SYSTEM_PROMPT_SETTING_KEY, clean_prompt)
        return RuntimePrompt(content=clean_prompt, source="runtime_settings")


class ClearUserChatContext:
    def __init__(self, chat_context_repository: ChatContextAdminRepository):
        self.chat_context_repository = chat_context_repository

    def execute(self, user_id: str) -> ChatContextClearResult:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise AdminValidationError("Missing user_id")

        deleted_messages, reset_conversations = (
            self.chat_context_repository.clear_user_chat_context(clean_user_id)
        )
        return ChatContextClearResult(
            deleted_messages=deleted_messages,
            reset_conversations=reset_conversations,
        )
