from dataclasses import dataclass

SUPPORTED_VOICE_CONTENT_TYPES = frozenset({"audio/mpeg", "audio/mp3"})
VOICE_USER_MESSAGE_TYPE = "voice_asr"
VOICE_ASSISTANT_MESSAGE_TYPE = "voice_reply"


class UnsupportedVoiceFormatError(ValueError):
    """Raised when an uploaded voice file is not in a supported format."""


@dataclass(frozen=True)
class VoiceRecognitionResult:
    user_text: str


@dataclass(frozen=True)
class VoiceReplyResult:
    reply: str
    audio_url: str
