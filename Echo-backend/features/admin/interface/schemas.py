from pydantic import BaseModel


class RuntimePromptResponse(BaseModel):
    prompt: str
    source: str


class RuntimePromptUpdateRequest(BaseModel):
    prompt: str


class ClearChatContextRequest(BaseModel):
    user_id: str


class ClearChatContextResponse(BaseModel):
    deleted_messages: int
    reset_conversations: int
