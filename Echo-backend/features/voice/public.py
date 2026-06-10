from features.voice.application.use_cases import GenerateVoiceReply, RecognizeVoice
from features.voice.domain.entities import (
    UnsupportedVoiceFormatError,
    VoiceRecognitionResult,
    VoiceReplyResult,
)
from features.voice.infrastructure.container import (
    get_generate_voice_reply_use_case,
    get_recognize_voice_use_case,
)
from features.voice.infrastructure.audio_storage import (
    VoiceAudioCleanupResult,
    cleanup_expired_voice_audio_files,
)


async def recognize_voice(audio_bytes: bytes, content_type: str) -> VoiceRecognitionResult:
    use_case = get_recognize_voice_use_case()
    return await use_case.execute(audio_bytes=audio_bytes, content_type=content_type)


async def generate_voice_reply(user_id: str, message: str) -> VoiceReplyResult:
    use_case = get_generate_voice_reply_use_case()
    return await use_case.execute(user_id=user_id, message=message)


def cleanup_expired_voice_audio() -> VoiceAudioCleanupResult:
    return cleanup_expired_voice_audio_files()


__all__ = [
    "GenerateVoiceReply",
    "RecognizeVoice",
    "UnsupportedVoiceFormatError",
    "VoiceAudioCleanupResult",
    "VoiceRecognitionResult",
    "VoiceReplyResult",
    "cleanup_expired_voice_audio",
    "generate_voice_reply",
    "recognize_voice",
]
