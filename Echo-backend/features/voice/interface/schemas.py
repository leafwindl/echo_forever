from pydantic import BaseModel


class VoiceASRResponse(BaseModel):
    user_text: str


class VoiceReplyRequest(BaseModel):
    user_id: str
    message: str


class VoiceReplyResponse(BaseModel):
    reply: str
    audio_url: str
