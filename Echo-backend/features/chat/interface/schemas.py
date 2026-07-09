from typing import Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    input_type: Literal["text", "voice"] = "text"
    voice_reply_enabled: bool = False


class ChatResponse(BaseModel):
    reply: str
    audio_url: str | None = None
