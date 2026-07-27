from typing import Literal

from pydantic import BaseModel, Field, field_validator
from shared.config import settings


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    mode: Literal["chat", "call"] = "chat"

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("Message must not be empty")
        if len(clean_value) > settings.chat_message_max_chars:
            raise ValueError(f"Message exceeds {settings.chat_message_max_chars} characters")
        return value


class ChatResponse(BaseModel):
    reply: str
    audio_urls: list[str] = Field(default_factory=list)


class ClearChatResponse(BaseModel):
    deleted_messages: int
    reset_conversations: int
