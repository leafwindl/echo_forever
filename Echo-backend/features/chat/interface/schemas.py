from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from shared.config import settings


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    mode: Literal["call"] = "call"

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, value: str) -> str:
        clean_value = value.strip()
        if len(clean_value) > settings.chat_message_max_chars:
            raise ValueError(f"Message exceeds {settings.chat_message_max_chars} characters")
        return value

    @model_validator(mode="after")
    def validate_content(self):
        if not self.message.strip():
            raise ValueError("Message must not be empty")
        return self


class AsyncChatMessageRequest(BaseModel):
    client_message_id: UUID
    message_type: Literal["text", "sticker"]
    text: str = Field(default="", max_length=10000)
    sticker_id: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_content(self):
        clean_text = self.text.strip()
        clean_sticker_id = self.sticker_id.strip()
        if self.message_type == "text":
            if not clean_text:
                raise ValueError("Text message must not be empty")
            if clean_sticker_id:
                raise ValueError("Text message cannot include sticker_id")
        else:
            if not clean_sticker_id:
                raise ValueError("Sticker message requires sticker_id")
            if clean_text:
                raise ValueError("Sticker message cannot include text")
        return self


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
    stable_message_id: str = ""
    client_message_id: str = ""
    role: Literal["user", "assistant"]
    message_type: str
    content: str
    content_parts: list[ChatContentPart] = Field(default_factory=list)
    sources: list[ChatSource] = Field(default_factory=list)
    agent_turn_id: str = ""
    reply_group_id: str = ""
    sequence_in_group: int = 0
    in_reply_to_message_id: int | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    conversation_id: str
    items: list[ChatHistoryMessageResponse] = Field(default_factory=list)
    has_more: bool
    next_before_id: int | None = None
    next_after_id: int | None = None


class ChatAcceptedTurnResponse(BaseModel):
    turn_id: str
    status: str


class ChatMessageAcceptedResponse(BaseModel):
    conversation_id: str
    message: ChatHistoryMessageResponse
    turn: ChatAcceptedTurnResponse
    replayed: bool = False
