import asyncio
import logging
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from providers.tts_provider import get_tts_provider
from shared.config import settings

logger = logging.getLogger(__name__)

STREAM_TTL_SECONDS = 90


class _StreamingAudioTask:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes | Exception | None] = asyncio.Queue()
        self.producer_task: asyncio.Task[None] | None = None
        self.expiration_task: asyncio.Task[None] | None = None
        self.consumed = False


_audio_streams: dict[str, _StreamingAudioTask] = {}


async def _produce_audio(stream_id: str, audio_task: _StreamingAudioTask, text: str) -> None:
    total_bytes = 0
    started_at = time.perf_counter()
    try:
        provider = get_tts_provider()
        stream_method = getattr(provider, "stream_text_to_speech", None)
        if callable(stream_method):
            audio_stream = stream_method(text, settings.tts_voice_id)
            async for chunk in audio_stream:
                total_bytes += len(chunk)
                if total_bytes > settings.tts_audio_max_bytes:
                    raise ValueError("Streaming TTS response exceeds configured audio size limit")
                if chunk:
                    await audio_task.queue.put(chunk)
        else:
            result = await provider.text_to_speech(text, settings.tts_voice_id)
            audio_bytes = result if isinstance(result, bytes) else result.audio_bytes
            await audio_task.queue.put(audio_bytes)
            total_bytes = len(audio_bytes)
        logger.info(
            "Streaming TTS produced stream_id=%s text_length=%s audio_bytes=%s duration_ms=%.1f",
            stream_id,
            len(text),
            total_bytes,
            (time.perf_counter() - started_at) * 1000,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Streaming TTS failed stream_id=%s", stream_id)
        await audio_task.queue.put(exc)
    finally:
        await audio_task.queue.put(None)


async def _expire_stream(stream_id: str, audio_task: _StreamingAudioTask) -> None:
    await asyncio.sleep(STREAM_TTL_SECONDS)
    if _audio_streams.get(stream_id) is not audio_task:
        return
    _audio_streams.pop(stream_id, None)
    if audio_task.producer_task and not audio_task.producer_task.done():
        audio_task.producer_task.cancel()


async def start_streaming_tts(text: str) -> str:
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Streaming TTS text cannot be empty")

    stream_id = uuid4().hex
    audio_task = _StreamingAudioTask()
    _audio_streams[stream_id] = audio_task
    audio_task.producer_task = asyncio.create_task(
        _produce_audio(stream_id, audio_task, clean_text)
    )
    audio_task.expiration_task = asyncio.create_task(_expire_stream(stream_id, audio_task))
    return f"{settings.static_url_prefix.rstrip('/')}/voice/tts/stream/{stream_id}"


def consume_streaming_tts(stream_id: str) -> AsyncIterator[bytes]:
    audio_task = _audio_streams.get(stream_id)
    if audio_task is None or audio_task.consumed:
        raise KeyError(stream_id)
    audio_task.consumed = True

    async def iterate_audio() -> AsyncIterator[bytes]:
        try:
            while True:
                item = await audio_task.queue.get()
                if item is None:
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            _audio_streams.pop(stream_id, None)
            if audio_task.expiration_task and not audio_task.expiration_task.done():
                audio_task.expiration_task.cancel()
            if audio_task.producer_task and not audio_task.producer_task.done():
                audio_task.producer_task.cancel()

    return iterate_audio()
