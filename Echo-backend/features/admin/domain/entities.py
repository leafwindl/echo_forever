from dataclasses import dataclass


SYSTEM_PROMPT_SETTING_KEY = "system_prompt"


@dataclass(frozen=True)
class RuntimePrompt:
    content: str
    source: str


@dataclass(frozen=True)
class ChatContextClearResult:
    deleted_messages: int
    reset_conversations: int
