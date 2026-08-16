from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from features.agent.domain.delivery import validate_agent_delivery_segments
from features.devices.application.latency import DeviceLatencyTracker
from features.devices.application.sentence_chunker import SentenceChunker
from features.devices.application.transcript_guard import is_plausible_device_transcript
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

_NON_ACTIONABLE_FILLERS = frozenset("嗯啊呃额唔")
_FILLER_PUNCTUATION = frozenset("。！？!?，,、；;：:… .")
_TTS_EMPTY_AUDIO_RETRY_DELAY_SECONDS = 0.35


def is_actionable_device_text(text: str) -> bool:
    """Reject filler-only noise that commonly comes from an open microphone."""
    clean_text = text.strip()
    if not clean_text:
        return False
    return not all(
        character in _NON_ACTIONABLE_FILLERS or character in _FILLER_PUNCTUATION
        for character in clean_text
    )


@dataclass(frozen=True)
class _QueuedPhrase:
    text: str
    audio_task: asyncio.Task[tuple[bytes, ...]] | None = None


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
        chunk_min_chars: int = 12,
        prefetch_phrases: int = 1,
    ):
        self.recognizer = recognizer
        self.conversation = conversation
        self.speech = speech
        self.notifier = notifier
        self.chunk_max_chars = chunk_max_chars
        self.chunk_min_chars = chunk_min_chars
        self.queue_max_packets = queue_max_packets
        self.prefetch_phrases = max(0, prefetch_phrases)

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
        if not is_plausible_device_transcript(user_text, len(pcm16_audio)):
            logger.warning(
                "Echo device rejected implausible transcript request_id=%s "
                "text_length=%s audio_duration_ms=%.1f",
                request_id,
                len(user_text),
                len(pcm16_audio) * 1000 / (16000 * 2),
            )
            raise ValueError("Device speech transcript is implausibly long")
        if latency is not None:
            latency.mark("asr_final")
        if not is_actionable_device_text(user_text):
            if latency is not None:
                latency.mark("turn_complete")
            logger.info(
                "Echo device ignored filler-only recognition request_id=%s text_length=%s",
                request_id,
                len(user_text),
            )
            return DeviceTurnResult(user_text=user_text, reply="", audio_urls=())
        await on_recognized(user_text)

        phrase_queue: asyncio.Queue[_QueuedPhrase | None] = asyncio.Queue(
            maxsize=max(1, self.queue_max_packets // 4)
        )
        chunker = SentenceChunker(
            max_chars=self.chunk_max_chars,
            min_chars=self.chunk_min_chars,
        )
        tts_started = False
        delta_received = False
        first_sentence_ready = False
        phrase_index = 0
        prefetch_slots = asyncio.Semaphore(max(1, self.prefetch_phrases))
        prefetch_tasks: set[asyncio.Task[tuple[bytes, ...]]] = set()

        async def collect_prefetched_audio(text: str, index: int) -> tuple[bytes, ...]:
            started_at = time.perf_counter()
            chunks: list[bytes] = []
            for attempt in range(2):
                chunks = []
                try:
                    async with prefetch_slots:
                        async for chunk in self.speech.stream_pcm16(text):
                            chunks.append(chunk)
                    break
                except Exception:
                    if attempt > 0:
                        raise
                    logger.warning(
                        "Echo device TTS prefetch retry request_id=%s phrase_index=%s",
                        request_id,
                        index,
                        exc_info=True,
                    )
                    await asyncio.sleep(_TTS_EMPTY_AUDIO_RETRY_DELAY_SECONDS)
            logger.info(
                "Echo device TTS phrase prefetched request_id=%s phrase_index=%s "
                "text_length=%s chunks=%s bytes=%s duration_ms=%.1f",
                request_id,
                index,
                len(text),
                len(chunks),
                sum(len(chunk) for chunk in chunks),
                (time.perf_counter() - started_at) * 1000,
            )
            return tuple(chunks)

        async def enqueue_phrase(phrase: str) -> None:
            nonlocal first_sentence_ready, phrase_index
            if not phrase:
                return
            validate_agent_delivery_segments((phrase,))
            if not first_sentence_ready and latency is not None:
                first_sentence_ready = True
                latency.mark("llm_first_sentence")

            current_index = phrase_index
            phrase_index += 1
            audio_task: asyncio.Task[tuple[bytes, ...]] | None = None
            if current_index > 0 and self.prefetch_phrases > 0:
                audio_task = asyncio.create_task(
                    collect_prefetched_audio(phrase, current_index)
                )
                prefetch_tasks.add(audio_task)
            await phrase_queue.put(_QueuedPhrase(text=phrase, audio_task=audio_task))

        async def on_text_delta(delta: str) -> None:
            nonlocal delta_received
            if delta:
                if not delta_received and latency is not None:
                    latency.mark("llm_first_delta")
                delta_received = True
            for phrase in chunker.push(delta):
                await enqueue_phrase(phrase)

        async def on_progress_text(text: str) -> None:
            clean_text = text.strip()
            if not clean_text:
                return
            validate_agent_delivery_segments((clean_text,))
            await enqueue_phrase(clean_text)

        async def consume_phrases() -> None:
            nonlocal tts_started
            from features.devices.infrastructure.audio_codec import StreamingPcmOpusEncoder

            encoder = StreamingPcmOpusEncoder(sample_rate=24000, frame_duration_ms=60)
            first_pcm_received = False

            async def emit_pcm_chunk(pcm16_chunk: bytes) -> None:
                nonlocal first_pcm_received
                if not first_pcm_received:
                    first_pcm_received = True
                    if latency is not None:
                        latency.mark("tts_first_pcm")
                for packet in encoder.push(pcm16_chunk):
                    await on_audio_packet(packet)

            try:
                while True:
                    queued_phrase = await phrase_queue.get()
                    if queued_phrase is None:
                        break
                    if not tts_started:
                        tts_started = True
                        await on_tts_start()
                    await on_sentence_start(queued_phrase.text)
                    if queued_phrase.audio_task is None:
                        audio_received = False
                        for attempt in range(2):
                            try:
                                async for pcm16_chunk in self.speech.stream_pcm16(
                                    queued_phrase.text
                                ):
                                    audio_received = True
                                    await emit_pcm_chunk(pcm16_chunk)
                                break
                            except Exception:
                                if audio_received or attempt > 0:
                                    raise
                                logger.warning(
                                    "Echo device initial TTS retry request_id=%s",
                                    request_id,
                                    exc_info=True,
                                )
                                await asyncio.sleep(_TTS_EMPTY_AUDIO_RETRY_DELAY_SECONDS)
                    else:
                        for pcm16_chunk in await queued_phrase.audio_task:
                            await emit_pcm_chunk(pcm16_chunk)
                for packet in encoder.finish():
                    await on_audio_packet(packet)
            finally:
                if tts_started:
                    with suppress(Exception):
                        await on_tts_stop()

        consumer_task = asyncio.create_task(consume_phrases())
        started_at = time.perf_counter()
        try:
            result = await self.conversation.reply(
                user_id=user_id,
                user_text=user_text,
                request_id=request_id,
                on_reply_delta=on_text_delta,
                on_progress_text=on_progress_text,
                synthesize_voice=False,
            )
            if latency is not None:
                latency.mark("reply_persisted")
            if not delta_received and result.reply.strip():
                for phrase in chunker.push(result.reply):
                    await enqueue_phrase(phrase)
            for phrase in chunker.finish():
                await enqueue_phrase(phrase)
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
            for task in tuple(prefetch_tasks):
                task.cancel()
            if prefetch_tasks:
                await asyncio.gather(*prefetch_tasks, return_exceptions=True)
            with suppress(asyncio.CancelledError, Exception):
                await consumer_task
            raise
