import logging

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.entities import ChatReplyDeliveryResult
from features.chat.domain.services import ChatVoiceReplySynthesizer

logger = logging.getLogger(__name__)

CHAT_INPUT_TYPE_TEXT = "text"
CHAT_INPUT_TYPE_VOICE = "voice"
VOICE_USER_MESSAGE_TYPE = "voice_asr"
VOICE_ASSISTANT_MESSAGE_TYPE = "voice_reply"


class SendChatMessage:
    def __init__(
        self,
        chat_reply_generator: GenerateChatReply,
        voice_reply_synthesizer: ChatVoiceReplySynthesizer,
    ):
        self.chat_reply_generator = chat_reply_generator
        self.voice_reply_synthesizer = voice_reply_synthesizer

    async def execute(
        self,
        user_id: str,
        message: str,
        input_type: str = CHAT_INPUT_TYPE_TEXT,
        voice_reply_enabled: bool = False,
    ) -> ChatReplyDeliveryResult:
        clean_input_type = input_type.strip().lower()
        if clean_input_type not in {CHAT_INPUT_TYPE_TEXT, CHAT_INPUT_TYPE_VOICE}:
            raise ValueError("input_type must be text or voice")

        user_message_type = (
            VOICE_USER_MESSAGE_TYPE if clean_input_type == CHAT_INPUT_TYPE_VOICE else "text"
        )
        assistant_message_type = VOICE_ASSISTANT_MESSAGE_TYPE if voice_reply_enabled else "text"

        chat_result = await self.chat_reply_generator.execute(
            user_id=user_id,
            message=message,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
        )

        audio_url = None
        if voice_reply_enabled:
            try:
                audio_url = await self.voice_reply_synthesizer.synthesize_reply(chat_result.reply)
            except Exception:
                # TTS 是体验增强能力，失败时保留文字回复和已完成的聊天落库。
                logger.exception("Voice synthesis failed for chat response")

        return ChatReplyDeliveryResult(reply=chat_result.reply, audio_url=audio_url)
