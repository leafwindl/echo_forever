import logging

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.entities import (
    CONVERSATION_MODES,
    ChatReplyDeliveryResult,
    ChatRequestInProgressError,
)
from features.chat.domain.services import ChatRequestGuard, ChatVoiceReplySynthesizer

logger = logging.getLogger(__name__)

VOICE_USER_MESSAGE_TYPE = "voice_asr"
VOICE_ASSISTANT_MESSAGE_TYPE = "voice_reply"


class SendChatMessage:
    def __init__(
        self,
        chat_reply_generator: GenerateChatReply,
        voice_reply_synthesizer: ChatVoiceReplySynthesizer,
        request_guard: ChatRequestGuard,
    ):
        self.chat_reply_generator = chat_reply_generator
        self.voice_reply_synthesizer = voice_reply_synthesizer
        self.request_guard = request_guard

    async def execute(
        self,
        user_id: str,
        message: str,
        conversation_mode: str = "chat",
    ) -> ChatReplyDeliveryResult:
        clean_user_id = user_id.strip()
        clean_mode = conversation_mode.strip().lower()
        if clean_mode not in CONVERSATION_MODES:
            raise ValueError("conversation_mode must be chat or call")

        if not self.request_guard.try_acquire(clean_user_id):
            raise ChatRequestInProgressError("上一条消息还在处理中，请稍后再试")

        is_call = clean_mode == "call"
        user_message_type = VOICE_USER_MESSAGE_TYPE if is_call else "text"
        assistant_message_type = VOICE_ASSISTANT_MESSAGE_TYPE if is_call else "text"

        try:
            chat_result = await self.chat_reply_generator.execute(
                user_id=clean_user_id,
                message=message,
                user_message_type=user_message_type,
                assistant_message_type=assistant_message_type,
                conversation_mode=clean_mode,
            )

            audio_urls: tuple[str, ...] = ()
            if is_call:
                try:
                    synthesis_result = await self.voice_reply_synthesizer.synthesize_reply(
                        chat_result.reply
                    )
                    audio_urls = (
                        (synthesis_result,)
                        if isinstance(synthesis_result, str)
                        else tuple(synthesis_result)
                    )
                except Exception:
                    # TTS is an enhancement; text reply and persisted chat turn still stand.
                    logger.exception("Voice synthesis failed for chat response")

            return ChatReplyDeliveryResult(reply=chat_result.reply, audio_urls=audio_urls)
        finally:
            self.request_guard.release(clean_user_id)
