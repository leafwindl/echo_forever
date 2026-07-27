from dataclasses import dataclass

SUPPORTED_VOICE_CONTENT_TYPES = frozenset({"audio/mpeg", "audio/mp3"})


class UnsupportedVoiceFormatError(ValueError):
    """Raised when an uploaded voice file is not in a supported format."""


@dataclass(frozen=True)
class VoiceRecognitionResult:
    user_text: str


@dataclass(frozen=True)
class SynthesizedVoiceAudio:
    audio_bytes: bytes
    file_suffix: str
    content_type: str


@dataclass(frozen=True)
class VoiceSynthesisResult:
    audio_urls: tuple[str, ...]


@dataclass(frozen=True)
class StreamingRecognitionUpdate:
    text: str
    is_final: bool = False
