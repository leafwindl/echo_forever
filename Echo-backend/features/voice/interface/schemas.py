from pydantic import BaseModel


class VoiceASRResponse(BaseModel):
    user_text: str
