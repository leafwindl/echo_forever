from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from features.devices.application.latency import DeviceLatencyTracker
from features.devices.application.sentence_chunker import SentenceChunker
from features.devices.domain.entities import DeviceTurnResult
from features.devices.domain.services import (
    DeviceChatNotifier,
    DeviceConversationService,
    DeviceSpeechSynthesizer,
    DeviceVoiceRecognizer,
)

logger = logging.getLogger(__name__)

TextCallback = Callable[[str], Awaitable[None]]
PacketCallback = Callable[[bytes], Awaitable[None]]
EventCallback = Callable[[], Awaitable[None]]


class StreamDeviceVoiceTurn:
    """Run one device turn while handing completed text phrases to TTS."""

    def __init__(
        self,
        *,
        recognizer: DeviceVoiceRecognizer,
        conversation: DeviceConversationService,
        speech: DeviceSpeechSynthesizer,
        notifier: DeviceChatNotifier,
        chunk_max_chars: int,
        queue_max_packets: int,
    ):
        self.recognizer = recognizer
        self.conversation = conversation
        self.speech = speech
        self.notifier = notifier
        self.chunk_max_chars = chunk_max_chars
        self.queue_max_packets = queue_max_packets

    async def execute(
        self,
        *,
        user_id: str,
        pcm16_audio: bytes,
        request_id: str,
        on_recognized: TextCallback,
        on_tts_start: EventCallback,
        on_sentence_start: Callable[[str], Awaitable[None]],
        on_audio_packet: PacketCallback,
        on_tts_stop: EventCallback,
        recognized_text: str | None = None,
        latency: DeviceLatencyTracker | None = None,
    ) -> DeviceTurnResult:
        if not user_id.strip():
            raise ValueError("Device is not mapped to an Echo user")
        if not pcm16_audio:
            raise ValueError("Device audio is empty")

        user_text = (recognized_text or "").strip()
        if not user_text:
            user_text = (await self.recognizer.recognize_pcm16(pcm16_audio)).strip()
        if not user_text:
            raise ValueError("Device speech was not recognized")
        if latency is not None:
            latency.mark("asr_final")
        await on_recognized(user_text)

        phrase_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=max(1, self.queue_max_packets // 4)
        )
        chunker = SentenceChunker(max_chars=self.chunk_max_chars)
        tts_started = False
        delta_received = False
        first_sentence_ready = False

        async def on_text_delta(delta: str) -> None:
            nonlocal delta_received, first_sentence_ready
            if delta:
                if not delta_received and latency is not None:
                    latency.mark("llm_first_delta")
                delta_received = True
            for phrase in chunker.push(delta):
                if phrase:
                    if not first_sentence_ready and latency is not None:
                        first_sentence_ready = True
                        latency.mark("llm_first_sentence")
                    await phrase_queue.put(phrase)

        async def consume_phrases() -> None:
            nonlocal tts_started
            from features.devices.infrastructure.audio_codec import StreamingPcmOpusEncoder

            encoder = StreamingPcmOpusEncoder(sample_rate=24000, frame_duration_ms=60)
            first_pcm_received = False
            while True:
                phrase = await phrase_queue.get()
                if phrase is None:
                    break
                if not tts_started:
                    tts_started = True
                    await on_tts_start()
                await on_sentence_start(phrase)
                async for pcm16_chunk in self.speech.stream_pcm16(phrase):
                    if not first_pcm_received:
                        first_pcm_received = True
                        if latency is not None:
                            latency.mark("tts_first_pcm")
                    for packet in encoder.push(pcm16_chunk):
                        await on_audio_packet(packet)
            for packet in encoder.finish():
                await on_audio_packet(packet)
            if tts_started:
                await on_tts_stop()

        consumer_task = asyncio.create_task(consume_phrases())
        started_at = time.perf_counter()
        try:
            result = await self.conversation.reply(
                user_id=user_id,
                user_text=user_text,
                request_id=request_id,
                on_reply_delta=on_text_delta,
                synthesize_voice=False,
            )
            if latency is not None:
                latency.mark("reply_persisted")
            if not delta_received and result.reply.strip():
                for phrase in chunker.push(result.reply):
                    if phrase and not first_sentence_ready and latency is not None:
                        first_sentence_ready = True
                        latency.mark("llm_first_sentence")
                    await phrase_queue.put(phrase)
            for phrase in chunker.finish():
                if phrase and not first_sentence_ready and latency is not None:
                    first_sentence_ready = True
                    latency.mark("llm_first_sentence")
                await phrase_queue.put(phrase)
            await phrase_queue.put(None)
            await consumer_task
            await self.notifier.notify_latest_turn(user_id)
            if latency is not None:
                latency.mark("app_notified")
                latency.mark("turn_complete")
            logger.info(
                "Echo streaming device turn completed input_bytes=%s "
                "audio_duration_ms=%.1f duration_ms=%.1f",
                len(pcm16_audio),
                len(pcm16_audio) * 1000 / (16000 * 2),
                (time.perf_counter() - started_at) * 1000,
            )
            return result
        except BaseException:
            if not consumer_task.done():
                consumer_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await consumer_task
            raise
