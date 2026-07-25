from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shared.config import settings


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10000)
    input_type: Literal["text", "voice"] = "text"
    voice_reply_enabled: bool = False

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
    audio_url: str | None = None


class ClearChatResponse(BaseModel):
    deleted_messages: int
    reset_conversations: int
