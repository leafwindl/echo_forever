from providers.asr_provider import get_asr_provider
from providers.tts_provider import get_tts_provider
from shared.config import settings

from features.voice.domain.entities import SynthesizedVoiceAudio
from features.voice.domain.services import (
    VoiceAudioStorage,
    VoiceRecognizer,
    VoiceSynthesizer,
)
from features.voice.infrastructure.audio_storage import (
    delete_upload_audio_file,
    save_audio_file,
    save_upload_audio_file,
)


class LocalVoiceAudioStorage(VoiceAudioStorage):
    def save_upload(self, audio_bytes: bytes, suffix: str = ".mp3") -> str:
        return save_upload_audio_file(audio_bytes, suffix=suffix)

    def delete_upload(self, audio_path: str) -> None:
        delete_upload_audio_file(audio_path)

    async def save_generated_audio(self, audio_bytes: bytes, suffix: str = ".mp3") -> str:
        return await save_audio_file(audio_bytes, suffix=suffix)


class TencentVoiceRecognizer(VoiceRecognizer):
    async def recognize(self, audio_path: str) -> str:
        provider = get_asr_provider()
        return await provider.recognize(audio_path)


class ProviderVoiceSynthesizer(VoiceSynthesizer):
    async def synthesize(
        self,
        text: str,
        instruction: str | None = None,
    ) -> SynthesizedVoiceAudio:
        provider = get_tts_provider()
        result = await provider.text_to_speech(
            text,
            settings.tts_voice_id,
            instruction=instruction,
        )
        return SynthesizedVoiceAudio(
            audio_bytes=result.audio_bytes,
            file_suffix=result.file_suffix,
            content_type=result.content_type,
        )
