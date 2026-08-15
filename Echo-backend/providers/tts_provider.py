import asyncio
import io
import logging
import threading
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast

import av
import dashscope
import edge_tts
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
from shared.config import settings

from providers.registry import get_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TTSOutput:
    audio_bytes: bytes
    file_suffix: str
    content_type: str


class TTSProvider(Protocol):
    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> TTSOutput: ...

    def stream_text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]: ...

    def stream_pcm16(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]: ...


class EdgeTTSProvider:
    async def stream_text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]:
        del instruction  # Edge TTS does not support per-request delivery instructions.
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("TTS text cannot be empty")

        try:
            communicate = edge_tts.Communicate(clean_text, voice_id)
            audio_received = False
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_received = True
                    yield chunk["data"]
            if not audio_received:
                raise ValueError("Edge TTS returned empty audio")
        except Exception as exc:
            raise ValueError(f"Edge TTS error: {exc}") from exc

    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> TTSOutput:
        audio_buffer = bytearray()
        async for chunk in self.stream_text_to_speech(text, voice_id, instruction=instruction):
            if len(audio_buffer) + len(chunk) > settings.tts_audio_max_bytes:
                raise ValueError("Edge TTS response exceeds configured audio size limit")
            audio_buffer.extend(chunk)
        return TTSOutput(
            audio_bytes=bytes(audio_buffer),
            file_suffix=".mp3",
            content_type="audio/mpeg",
        )

    async def stream_pcm16(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]:
        audio = bytearray()
        async for chunk in self.stream_text_to_speech(text, voice_id, instruction=instruction):
            audio.extend(chunk)
        with av.open(io.BytesIO(bytes(audio)), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                raise ValueError("Edge TTS returned no audio stream")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
            for decoded in container.decode(stream):
                for frame in resampler.resample(decoded):
                    yield bytes(frame.planes[0])[: frame.samples * 2]
            for frame in resampler.resample(None):
                yield bytes(frame.planes[0])[: frame.samples * 2]


class _CosyVoiceResultCallback(ResultCallback):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._loop = loop
        self._queue = queue
        self._finish_lock = threading.Lock()
        self._finished = False

    def _publish(self, item: bytes | Exception | None) -> None:
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def finish(self) -> None:
        with self._finish_lock:
            if self._finished:
                return
            self._finished = True
        self._publish(None)

    def fail(self, error: Exception) -> None:
        self._publish(error)
        self.finish()

    def on_data(self, data: bytes) -> None:
        if data:
            self._publish(data)

    def on_error(self, message: str) -> None:
        self.fail(ValueError(f"CosyVoice synthesis failed: {message}"))

    def on_complete(self) -> None:
        self.finish()


class CosyVoiceTTSProvider:
    @staticmethod
    def _endpoint() -> str:
        custom_endpoint = settings.cosyvoice_websocket_url.strip()
        workspace_id = settings.dashscope_workspace_id.strip()
        if custom_endpoint:
            endpoint = custom_endpoint
        elif workspace_id:
            endpoint = f"wss://{workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
        else:
            raise ValueError("CosyVoice requires DASHSCOPE_WORKSPACE_ID")
        if not endpoint.startswith("wss://"):
            raise ValueError("COSYVOICE_WEBSOCKET_URL must use wss://")
        return endpoint

    @staticmethod
    def _validate_config(voice_id: str) -> tuple[str, str, str]:
        api_key = settings.dashscope_api_key.strip()
        model = settings.cosyvoice_model.strip()
        clean_voice_id = voice_id.strip()
        missing: list[str] = []
        if not api_key:
            missing.append("DASHSCOPE_API_KEY")
        if (
            not settings.dashscope_workspace_id.strip()
            and not settings.cosyvoice_websocket_url.strip()
        ):
            missing.append("DASHSCOPE_WORKSPACE_ID")
        if not model:
            missing.append("COSYVOICE_MODEL")
        if not clean_voice_id:
            missing.append("TTS_VOICE_ID")
        if missing:
            raise ValueError(f"CosyVoice missing configuration: {', '.join(missing)}")
        return api_key, model, clean_voice_id

    async def _stream_audio(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
        audio_format: str = AudioFormat.MP3_22050HZ_MONO_256KBPS,
    ) -> AsyncIterator[bytes]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("TTS text cannot be empty")

        api_key, model, clean_voice_id = self._validate_config(voice_id)
        endpoint = self._endpoint()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | Exception | None] = asyncio.Queue()
        callback = _CosyVoiceResultCallback(loop, queue)
        synthesizer_state: dict[str, SpeechSynthesizer | bool] = {}
        started_at = time.perf_counter()

        def synthesize() -> None:
            try:
                dashscope.api_key = api_key
                synthesizer = SpeechSynthesizer(
                    model=model,
                    voice=clean_voice_id,
                    format=audio_format,
                    volume=settings.cosyvoice_volume,
                    speech_rate=settings.tts_speed,
                    pitch_rate=settings.cosyvoice_pitch_rate,
                    instruction=(instruction or settings.cosyvoice_instruction).strip() or None,
                    workspace=settings.dashscope_workspace_id.strip() or None,
                    url=endpoint,
                    callback=callback,
                )
                synthesizer_state["instance"] = synthesizer
                synthesizer_state["started"] = True
                synthesizer.streaming_call(clean_text)
                synthesizer.streaming_complete()
            except Exception as exc:
                callback.fail(ValueError(f"CosyVoice request failed: {exc}"))
            finally:
                callback.finish()

        worker = asyncio.create_task(asyncio.to_thread(synthesize))
        audio_received = False
        first_audio_logged = False
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(),
                        timeout=settings.cosyvoice_timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise ValueError("CosyVoice audio stream timed out") from exc
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                audio_received = True
                if not first_audio_logged:
                    first_audio_logged = True
                    logger.info(
                        "CosyVoice first audio model=%s text_length=%s duration_ms=%.1f",
                        model,
                        len(clean_text),
                        (time.perf_counter() - started_at) * 1000,
                    )
                yield item

            await worker
            if not audio_received:
                raise ValueError("CosyVoice returned empty audio")

            synthesizer = synthesizer_state.get("instance")
            logger.info(
                "CosyVoice synthesis completed model=%s request_id=%s sdk_first_packet_ms=%s "
                "duration_ms=%.1f",
                model,
                (
                    synthesizer.get_last_request_id()
                    if isinstance(synthesizer, SpeechSynthesizer)
                    else "unknown"
                ),
                (
                    synthesizer.get_first_package_delay()
                    if isinstance(synthesizer, SpeechSynthesizer)
                    else "unknown"
                ),
                (time.perf_counter() - started_at) * 1000,
            )
        finally:
            if not worker.done():
                synthesizer = synthesizer_state.get("instance")
                if (
                    isinstance(synthesizer, SpeechSynthesizer)
                    and synthesizer_state.get("started") is True
                ):
                    try:
                        await asyncio.to_thread(synthesizer.streaming_cancel, 1000)
                    except Exception:
                        logger.warning("Failed to cancel CosyVoice stream", exc_info=True)
                try:
                    await asyncio.wait_for(asyncio.shield(worker), timeout=2)
                except (TimeoutError, asyncio.CancelledError):
                    worker.cancel()
                except Exception:
                    logger.debug("CosyVoice worker stopped with an error", exc_info=True)

    async def stream_text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]:
        async for chunk in self._stream_audio(
            text,
            voice_id,
            instruction=instruction,
            audio_format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
        ):
            yield chunk

    async def stream_pcm16(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> AsyncIterator[bytes]:
        async for chunk in self._stream_audio(
            text,
            voice_id,
            instruction=instruction,
            audio_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        ):
            yield chunk

    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        instruction: str | None = None,
    ) -> TTSOutput:
        audio_buffer = bytearray()
        async for chunk in self.stream_text_to_speech(
            text,
            voice_id,
            instruction=instruction,
        ):
            if len(audio_buffer) + len(chunk) > settings.tts_audio_max_bytes:
                raise ValueError("CosyVoice response exceeds configured audio size limit")
            audio_buffer.extend(chunk)
        return TTSOutput(
            audio_bytes=bytes(audio_buffer),
            file_suffix=".mp3",
            content_type="audio/mpeg",
        )


def get_tts_provider() -> TTSProvider:
    provider_name = settings.tts_provider.strip().lower()
    if provider_name == "edge":
        return cast(TTSProvider, get_provider("tts", EdgeTTSProvider))
    if provider_name in {"cosyvoice", "cosyvoice-v3.5-flash"}:
        return cast(TTSProvider, get_provider("tts", CosyVoiceTTSProvider))
    raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")
