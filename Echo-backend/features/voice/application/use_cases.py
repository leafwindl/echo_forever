import logging

from features.voice.domain.entities import (
    SUPPORTED_VOICE_CONTENT_TYPES,
    UnsupportedVoiceFormatError,
    VoiceRecognitionResult,
    VoiceSynthesisResult,
)
from features.voice.domain.segmentation import split_text_for_speech
from features.voice.domain.services import (
    VoiceAudioStorage,
    VoiceRecognizer,
    VoiceStreamingRecognitionSession,
    VoiceStreamingRecognizer,
    VoiceSynthesizer,
)

logger = logging.getLogger(__name__)


class RecognizeVoice:
    def __init__(self, audio_storage: VoiceAudioStorage, recognizer: VoiceRecognizer):
        self.audio_storage = audio_storage
        self.recognizer = recognizer

    async def execute(self, audio_bytes: bytes, content_type: str) -> VoiceRecognitionResult:
        if content_type not in SUPPORTED_VOICE_CONTENT_TYPES:
            raise UnsupportedVoiceFormatError("仅支持 MP3 音频格式")
        if not audio_bytes:
            raise ValueError("Voice audio cannot be empty")

        audio_path = self.audio_storage.save_upload(audio_bytes, suffix=".mp3")
        try:
            user_text = await self.recognizer.recognize(audio_path)
        finally:
            try:
                self.audio_storage.delete_upload(audio_path)
            except Exception:
                logger.warning("Failed to cleanup voice upload: %s", audio_path, exc_info=True)
        logger.info("Voice ASR completed text_length=%s", len(user_text))
        return VoiceRecognitionResult(user_text=user_text)


class SynthesizeVoiceReply:
    def __init__(
        self,
        synthesizer: VoiceSynthesizer,
        audio_storage: VoiceAudioStorage,
        segment_max_chars: int = 80,
        reply_max_chars: int = 600,
    ):
        self.synthesizer = synthesizer
        self.audio_storage = audio_storage
        self.segment_max_chars = segment_max_chars
        self.reply_max_chars = reply_max_chars

    async def execute(self, text: str) -> VoiceSynthesisResult:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Voice synthesis text cannot be empty")

        segments = split_text_for_speech(
            clean_text,
            max_chars=self.segment_max_chars,
            total_max_chars=self.reply_max_chars,
        )
        audio_urls: list[str] = []
        for segment in segments:
            audio = await self.synthesizer.synthesize(segment)
            if isinstance(audio, bytes):
                # Compatibility for existing custom synthesizers during rollout.
                audio_url = await self.audio_storage.save_generated_audio(audio)
            else:
                audio_url = await self.audio_storage.save_generated_audio(
                    audio.audio_bytes,
                    suffix=audio.file_suffix,
                )
            audio_urls.append(audio_url)
        return VoiceSynthesisResult(audio_urls=tuple(audio_urls))


class OpenStreamingVoiceRecognition:
    def __init__(self, recognizer: VoiceStreamingRecognizer):
        self.recognizer = recognizer

    async def execute(self) -> VoiceStreamingRecognitionSession:
        return await self.recognizer.open_session()
