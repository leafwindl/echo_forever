from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from shared.config import settings


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=10000)
    mode: Literal["chat", "call"] = "chat"
    content_parts: list["ChatRequestContentPart"] = Field(default_factory=list, max_length=1)

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, value: str) -> str:
        clean_value = value.strip()
        if len(clean_value) > settings.chat_message_max_chars:
            raise ValueError(f"Message exceeds {settings.chat_message_max_chars} characters")
        return value

    @model_validator(mode="after")
    def validate_content(self):
        if not self.message.strip() and not self.content_parts:
            raise ValueError("Message or content_parts must not be empty")
        if self.content_parts and self.mode != "chat":
            raise ValueError("Sticker messages are only supported in chat mode")
        return self


class ChatRequestContentPart(BaseModel):
    type: Literal["sticker"]
    sticker_id: str = Field(min_length=1, max_length=200)


class ChatResponse(BaseModel):
    reply: str
    audio_urls: list[str] = Field(default_factory=list)
    content_parts: list["ChatContentPart"] = Field(default_factory=list)
    sources: list["ChatSource"] = Field(default_factory=list)


class ChatContentPart(BaseModel):
    type: Literal["text", "sticker"]
    text: str = ""
    sticker_id: str = ""
    url: str = ""


class ChatSource(BaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None


class ClearChatResponse(BaseModel):
    deleted_messages: int
    reset_conversations: int


class ChatHistoryMessageResponse(BaseModel):
    message_id: int
    role: Literal["user", "assistant"]
    message_type: str
    content: str
    content_parts: list[ChatContentPart] = Field(default_factory=list)
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    conversation_id: str
    items: list[ChatHistoryMessageResponse] = Field(default_factory=list)
    has_more: bool
    next_before_id: int | None = None
