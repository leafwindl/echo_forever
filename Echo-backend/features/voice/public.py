from features.voice.application.use_cases import RecognizeVoice, SynthesizeVoiceReply
from features.voice.domain.entities import (
    UnsupportedVoiceFormatError,
    VoiceRecognitionResult,
    VoiceSynthesisResult,
)
from features.voice.infrastructure.container import (
    get_recognize_voice_use_case,
    get_synthesize_voice_reply_use_case,
)
from features.voice.infrastructure.audio_storage import (
    VoiceAudioCleanupResult,
    cleanup_expired_voice_audio_files,
)


async def recognize_voice(audio_bytes: bytes, content_type: str) -> VoiceRecognitionResult:
    use_case = get_recognize_voice_use_case()
    return await use_case.execute(audio_bytes=audio_bytes, content_type=content_type)


async def synthesize_voice_reply(text: str) -> VoiceSynthesisResult:
    use_case = get_synthesize_voice_reply_use_case()
    return await use_case.execute(text=text)


def cleanup_expired_voice_audio() -> VoiceAudioCleanupResult:
    return cleanup_expired_voice_audio_files()


__all__ = [
    "RecognizeVoice",
    "SynthesizeVoiceReply",
    "UnsupportedVoiceFormatError",
    "VoiceAudioCleanupResult",
    "VoiceRecognitionResult",
    "VoiceSynthesisResult",
    "cleanup_expired_voice_audio",
    "recognize_voice",
    "synthesize_voice_reply",
]
