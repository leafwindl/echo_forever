import logging

from features.voice.domain.entities import (
    SUPPORTED_VOICE_CONTENT_TYPES,
    UnsupportedVoiceFormatError,
    VoiceRecognitionResult,
    VoiceReplyResult,
)
from features.voice.domain.services import (
    VoiceAudioStorage,
    VoiceChatResponder,
    VoiceRecognizer,
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
        logger.info("Only ASR result: %s", user_text)
        return VoiceRecognitionResult(user_text=user_text)


class GenerateVoiceReply:
    def __init__(
        self,
        chat_responder: VoiceChatResponder,
        synthesizer: VoiceSynthesizer,
        audio_storage: VoiceAudioStorage,
    ):
        self.chat_responder = chat_responder
        self.synthesizer = synthesizer
        self.audio_storage = audio_storage

    async def execute(self, user_id: str, message: str) -> VoiceReplyResult:
        reply = await self.chat_responder.reply(user_id, message)
        audio_bytes = await self.synthesizer.synthesize(reply)
        audio_url = await self.audio_storage.save_generated_audio(audio_bytes)
        return VoiceReplyResult(reply=reply, audio_url=audio_url)
