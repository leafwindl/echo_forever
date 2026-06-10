from features.chat.public import generate_chat_reply
from features.voice.domain.entities import VOICE_ASSISTANT_MESSAGE_TYPE, VOICE_USER_MESSAGE_TYPE
from features.voice.domain.services import (
    VoiceAudioStorage,
    VoiceChatResponder,
    VoiceRecognizer,
    VoiceSynthesizer,
)
from features.voice.infrastructure.audio_storage import (
    delete_upload_audio_file,
    save_audio_file,
    save_upload_audio_file,
)
from providers.asr_provider import get_asr_provider
from providers.tts_provider import get_tts_provider
from shared.config import settings

DEFAULT_EDGE_TTS_VOICE_ID = settings.minimax_tts_voice_id


class LocalVoiceAudioStorage(VoiceAudioStorage):
    def save_upload(self, audio_bytes: bytes, suffix: str = ".mp3") -> str:
        return save_upload_audio_file(audio_bytes, suffix=suffix)

    def delete_upload(self, audio_path: str) -> None:
        delete_upload_audio_file(audio_path)

    async def save_generated_audio(self, audio_bytes: bytes) -> str:
        return await save_audio_file(audio_bytes)


class TencentVoiceRecognizer(VoiceRecognizer):
    async def recognize(self, audio_path: str) -> str:
        provider = get_asr_provider()
        return await provider.recognize(audio_path)


class EdgeVoiceSynthesizer(VoiceSynthesizer):
    async def synthesize(self, text: str) -> bytes:
        provider = get_tts_provider()
        return await provider.text_to_speech(text, DEFAULT_EDGE_TTS_VOICE_ID)


class ChatVoiceResponder(VoiceChatResponder):
    async def reply(self, user_id: str, message: str) -> str:
        result = await generate_chat_reply(
            user_id=user_id,
            message=message,
            user_message_type=VOICE_USER_MESSAGE_TYPE,
            assistant_message_type=VOICE_ASSISTANT_MESSAGE_TYPE,
        )
        return result.reply
