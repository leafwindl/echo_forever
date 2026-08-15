import logging
import time

from features.voice.domain.entities import (
    SUPPORTED_VOICE_CONTENT_TYPES,
    UnsupportedVoiceFormatError,
    VoiceRecognitionResult,
    VoiceSynthesisResult,
)
from features.voice.domain.services import (
    VoiceAudioStorage,
    VoiceRecognizer,
    VoiceStreamingRecognitionSession,
    VoiceStreamingRecognizer,
    VoiceSynthesizer,
)
from features.voice.domain.speech_delivery import prepare_speech_text

logger = logging.getLogger(__name__)


class RecognizeVoice:
    def __init__(self, audio_storage: VoiceAudioStorage, recognizer: VoiceRecognizer):
        self.audio_storage = audio_storage
        self.recognizer = recognizer

    async def execute(self, audio_bytes: bytes, content_type: str) -> VoiceRecognitionResult:
        normalized_content_type = content_type.partition(";")[0].strip().lower()
        if normalized_content_type not in SUPPORTED_VOICE_CONTENT_TYPES:
            raise UnsupportedVoiceFormatError("仅支持 16 kHz 单声道 PCM16LE 音频格式")
        if not audio_bytes:
            raise ValueError("Voice audio cannot be empty")
        if len(audio_bytes) % 2 != 0:
            raise ValueError("PCM16 audio must contain complete 16-bit samples")

        audio_duration_ms = len(audio_bytes) * 1000 / (16000 * 2)
        audio_path = self.audio_storage.save_upload(audio_bytes, suffix=".pcm")
        recognition_started_at = time.perf_counter()
        try:
            user_text = await self.recognizer.recognize(audio_path)
        finally:
            try:
                self.audio_storage.delete_upload(audio_path)
            except Exception:
                logger.warning("Failed to cleanup voice upload: %s", audio_path, exc_info=True)
        recognition_duration_ms = (time.perf_counter() - recognition_started_at) * 1000
        logger.info(
            "Voice ASR completed text_length=%s audio_bytes=%s audio_duration_ms=%.1f "
            "duration_ms=%.1f realtime_factor=%.4f",
            len(user_text),
            len(audio_bytes),
            audio_duration_ms,
            recognition_duration_ms,
            recognition_duration_ms / audio_duration_ms if audio_duration_ms else 0.0,
        )
        return VoiceRecognitionResult(user_text=user_text)


class SynthesizeVoiceReply:
    def __init__(
        self,
        synthesizer: VoiceSynthesizer,
        audio_storage: VoiceAudioStorage,
        reply_max_chars: int = 600,
    ):
        self.synthesizer = synthesizer
        self.audio_storage = audio_storage
        self.reply_max_chars = reply_max_chars

    async def execute(self, text: str) -> VoiceSynthesisResult:
        clean_text = prepare_speech_text(text, self.reply_max_chars)
        if not clean_text:
            raise ValueError("Voice synthesis text cannot be empty")

        synthesis_started_at = time.perf_counter()
        audio = await self.synthesizer.synthesize(clean_text)
        audio_url = await self.audio_storage.save_generated_audio(
            audio.audio_bytes,
            suffix=audio.file_suffix,
        )
        logger.info(
            "Voice TTS reply completed requests=1 text_length=%s duration_ms=%.1f",
            len(clean_text),
            (time.perf_counter() - synthesis_started_at) * 1000,
        )
        return VoiceSynthesisResult(audio_urls=(audio_url,))


class OpenStreamingVoiceRecognition:
    def __init__(self, recognizer: VoiceStreamingRecognizer):
        self.recognizer = recognizer

    async def execute(self) -> VoiceStreamingRecognitionSession:
        return await self.recognizer.open_session()
