import logging
import time
from collections.abc import Awaitable, Callable

from features.devices.domain.entities import DeviceTurnResult
from features.devices.domain.services import (
    DeviceChatNotifier,
    DeviceConversationService,
    DeviceVoiceRecognizer,
)

logger = logging.getLogger(__name__)


class ProcessDeviceVoiceTurn:
    """Recognize one completed utterance and run the existing Echo call flow."""

    def __init__(
        self,
        *,
        recognizer: DeviceVoiceRecognizer,
        conversation: DeviceConversationService,
        notifier: DeviceChatNotifier,
    ):
        self.recognizer = recognizer
        self.conversation = conversation
        self.notifier = notifier

    async def execute(
        self,
        *,
        user_id: str,
        pcm16_audio: bytes,
        request_id: str,
        on_recognized: Callable[[str], Awaitable[None]] | None = None,
        recognized_text: str | None = None,
    ) -> DeviceTurnResult:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ValueError("Device is not mapped to an Echo user")
        if not pcm16_audio:
            raise ValueError("Device audio is empty")

        started_at = time.perf_counter()
        audio_duration_ms = len(pcm16_audio) * 1000 / (16000 * 2)
        asr_started_at = time.perf_counter()
        user_text = (recognized_text or "").strip()
        if not user_text:
            user_text = (await self.recognizer.recognize_pcm16(pcm16_audio)).strip()
        asr_completed_at = time.perf_counter()
        if not user_text:
            raise ValueError("Device speech was not recognized")
        if on_recognized is not None:
            await on_recognized(user_text)

        conversation_started_at = time.perf_counter()
        result = await self.conversation.reply(
            user_id=clean_user_id,
            user_text=user_text,
            request_id=request_id,
        )
        conversation_completed_at = time.perf_counter()
        await self.notifier.notify_latest_turn(clean_user_id)
        completed_at = time.perf_counter()
        asr_duration_ms = (asr_completed_at - asr_started_at) * 1000
        logger.info(
            "Echo device voice turn prepared audio_bytes=%s audio_duration_ms=%.1f "
            "asr_mode=%s asr_ms=%.1f asr_realtime_factor=%.4f conversation_ms=%.1f "
            "notify_ms=%.1f total_ms=%.1f",
            len(pcm16_audio),
            audio_duration_ms,
            "streaming" if recognized_text else "batch",
            asr_duration_ms,
            asr_duration_ms / audio_duration_ms if audio_duration_ms else 0.0,
            (conversation_completed_at - conversation_started_at) * 1000,
            (completed_at - conversation_completed_at) * 1000,
            (completed_at - started_at) * 1000,
        )
        return result
