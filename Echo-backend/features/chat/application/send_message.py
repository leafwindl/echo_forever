import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.entities import ChatReplyDeliveryResult, ChatRequestInProgressError
from features.chat.domain.services import ChatRequestGuard, ChatVoiceReplySynthesizer

logger = logging.getLogger(__name__)

STREAMING_SPEECH_BOUNDARY = re.compile(r"[。！？!?；;\n]")
STREAMING_SPEECH_SOFT_BOUNDARY = re.compile(r"[，、,:：]")

CHAT_INPUT_TYPE_TEXT = "text"
CHAT_INPUT_TYPE_VOICE = "voice"
VOICE_USER_MESSAGE_TYPE = "voice_asr"
VOICE_ASSISTANT_MESSAGE_TYPE = "voice_reply"


class StreamingSpeechSegmenter:
    def __init__(self, max_chars: int = 24, total_max_chars: int = 600):
        self.max_chars = max_chars
        self.total_max_chars = total_max_chars
        self.buffer = ""
        self.accepted_chars = 0

    def push(self, delta: str) -> tuple[str, ...]:
        remaining = self.total_max_chars - self.accepted_chars
        if remaining <= 0:
            return ()
        accepted = delta[:remaining]
        self.accepted_chars += len(accepted)
        self.buffer += accepted
        return self._drain(allow_partial=False)

    def finish(self) -> tuple[str, ...]:
        return self._drain(allow_partial=True)

    def _drain(self, allow_partial: bool) -> tuple[str, ...]:
        segments: list[str] = []
        while self.buffer:
            boundary = STREAMING_SPEECH_BOUNDARY.search(self.buffer)
            if boundary and boundary.end() <= self.max_chars:
                split_at = boundary.end()
            elif len(self.buffer) >= self.max_chars:
                candidate = self.buffer[: self.max_chars]
                soft_boundaries = list(STREAMING_SPEECH_SOFT_BOUNDARY.finditer(candidate))
                split_at = soft_boundaries[-1].end() if soft_boundaries else self.max_chars
            elif allow_partial:
                split_at = len(self.buffer)
            else:
                break

            segment = self.buffer[:split_at].strip()
            self.buffer = self.buffer[split_at:]
            if segment:
                segments.append(segment)
        return tuple(segments)


class SendChatMessage:
    def __init__(
        self,
        chat_reply_generator: GenerateChatReply,
        voice_reply_synthesizer: ChatVoiceReplySynthesizer,
        request_guard: ChatRequestGuard,
        streaming_voice_segment_max_chars: int = 24,
        voice_reply_max_chars: int = 600,
    ):
        self.chat_reply_generator = chat_reply_generator
        self.voice_reply_synthesizer = voice_reply_synthesizer
        self.request_guard = request_guard
        self.streaming_voice_segment_max_chars = streaming_voice_segment_max_chars
        self.voice_reply_max_chars = voice_reply_max_chars

    async def execute(
        self,
        user_id: str,
        message: str,
        input_type: str = CHAT_INPUT_TYPE_TEXT,
        voice_reply_enabled: bool = False,
    ) -> ChatReplyDeliveryResult:
        clean_user_id = user_id.strip()
        clean_input_type = input_type.strip().lower()
        if clean_input_type not in {CHAT_INPUT_TYPE_TEXT, CHAT_INPUT_TYPE_VOICE}:
            raise ValueError("input_type must be text or voice")

        if not self.request_guard.try_acquire(clean_user_id):
            raise ChatRequestInProgressError("上一条消息还在处理中，请稍后再试")

        user_message_type = (
            VOICE_USER_MESSAGE_TYPE if clean_input_type == CHAT_INPUT_TYPE_VOICE else "text"
        )
        assistant_message_type = VOICE_ASSISTANT_MESSAGE_TYPE if voice_reply_enabled else "text"

        try:
            chat_result = await self.chat_reply_generator.execute(
                user_id=clean_user_id,
                message=message,
                user_message_type=user_message_type,
                assistant_message_type=assistant_message_type,
            )

            audio_urls: tuple[str, ...] = ()
            if voice_reply_enabled:
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

    async def execute_stream(
        self,
        user_id: str,
        message: str,
        on_text_delta: Callable[[str], Awaitable[None]],
        on_audio_ready: Callable[[str], Awaitable[None]],
        input_type: str = CHAT_INPUT_TYPE_TEXT,
        voice_reply_enabled: bool = False,
    ) -> ChatReplyDeliveryResult:
        clean_user_id = user_id.strip()
        clean_input_type = input_type.strip().lower()
        if clean_input_type not in {CHAT_INPUT_TYPE_TEXT, CHAT_INPUT_TYPE_VOICE}:
            raise ValueError("input_type must be text or voice")
        if not self.request_guard.try_acquire(clean_user_id):
            raise ChatRequestInProgressError("上一条消息还在处理中，请稍后再试")

        user_message_type = (
            VOICE_USER_MESSAGE_TYPE if clean_input_type == CHAT_INPUT_TYPE_VOICE else "text"
        )
        assistant_message_type = VOICE_ASSISTANT_MESSAGE_TYPE if voice_reply_enabled else "text"
        audio_urls: list[str] = []
        tts_queue: asyncio.Queue[str | None] | None = None
        tts_task: asyncio.Task[None] | None = None
        segmenter: StreamingSpeechSegmenter | None = None

        async def synthesize_segments() -> None:
            assert tts_queue is not None
            while True:
                segment = await tts_queue.get()
                if segment is None:
                    return
                try:
                    audio_url = await self.voice_reply_synthesizer.start_streaming_segment(
                        segment
                    )
                    audio_urls.append(audio_url)
                    await on_audio_ready(audio_url)
                except Exception:
                    logger.exception("Streaming voice synthesis segment failed")

        try:
            if voice_reply_enabled:
                segmenter = StreamingSpeechSegmenter(
                    max_chars=self.streaming_voice_segment_max_chars,
                    total_max_chars=self.voice_reply_max_chars,
                )
                tts_queue = asyncio.Queue()
                tts_task = asyncio.create_task(synthesize_segments())

            async def handle_delta(delta: str) -> None:
                await on_text_delta(delta)
                if segmenter is not None and tts_queue is not None:
                    for segment in segmenter.push(delta):
                        tts_queue.put_nowait(segment)

            chat_result = await self.chat_reply_generator.execute_stream(
                user_id=clean_user_id,
                message=message,
                on_delta=handle_delta,
                user_message_type=user_message_type,
                assistant_message_type=assistant_message_type,
            )
            if segmenter is not None and tts_queue is not None:
                for segment in segmenter.finish():
                    tts_queue.put_nowait(segment)
                tts_queue.put_nowait(None)
            if tts_task is not None:
                await tts_task
            return ChatReplyDeliveryResult(
                reply=chat_result.reply,
                audio_urls=tuple(audio_urls),
            )
        finally:
            if tts_task is not None and not tts_task.done():
                tts_task.cancel()
            self.request_guard.release(clean_user_id)
