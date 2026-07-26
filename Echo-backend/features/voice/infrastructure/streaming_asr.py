import asyncio
import json
import logging
from asyncio.subprocess import Process
from typing import Any
from uuid import uuid4

from shared.config import settings

from features.voice.domain.entities import StreamingRecognitionUpdate
from features.voice.domain.services import (
    VoiceStreamingRecognitionSession,
    VoiceStreamingRecognizer,
)

logger = logging.getLogger(__name__)

FUNASR_PCM_CHUNK_BYTES = 19_200


class FunASRTranscriptAccumulator:
    """Merge temporary online fragments with corrected 2-pass offline segments."""

    def __init__(self) -> None:
        self.confirmed_text = ""
        self.pending_online_text = ""

    @property
    def current_text(self) -> str:
        return f"{self.confirmed_text}{self.pending_online_text}".strip()

    def apply(self, payload: dict[str, Any]) -> StreamingRecognitionUpdate | None:
        text = str(payload.get("text") or "").strip()
        mode = str(payload.get("mode") or "")
        is_final = bool(payload.get("is_final"))

        if mode == "2pass-online":
            if not text:
                return None
            self.pending_online_text += text
            return StreamingRecognitionUpdate(text=self.current_text, is_final=False)

        if mode == "2pass-offline":
            if text:
                self.confirmed_text += text
            self.pending_online_text = ""
            return StreamingRecognitionUpdate(text=self.current_text, is_final=is_final)

        if not text and not is_final:
            return None
        if text:
            self.pending_online_text = text
        return StreamingRecognitionUpdate(text=self.current_text, is_final=is_final)


class FunASRStreamingRecognitionSession(VoiceStreamingRecognitionSession):
    def __init__(self, upstream: Any, ffmpeg: Process):
        self.upstream = upstream
        self.ffmpeg = ffmpeg
        self.update_queue: asyncio.Queue[StreamingRecognitionUpdate] = asyncio.Queue()
        self.final_event = asyncio.Event()
        self.transcript = FunASRTranscriptAccumulator()
        self.finished = False
        self.closed = False
        self.stderr_task = asyncio.create_task(self._read_ffmpeg_errors())
        self.pump_task = asyncio.create_task(self._pump_pcm_to_funasr())
        self.receive_task = asyncio.create_task(self._receive_funasr_updates())

    async def send_audio(self, audio_bytes: bytes) -> None:
        if self.finished or self.closed:
            raise RuntimeError("Streaming ASR session is no longer accepting audio")
        if not audio_bytes:
            return
        if self.ffmpeg.stdin is None:
            raise RuntimeError("FFmpeg input is unavailable")
        self.ffmpeg.stdin.write(audio_bytes)
        await self.ffmpeg.stdin.drain()

    async def finish(self) -> None:
        if self.finished:
            return
        self.finished = True

        if self.ffmpeg.stdin is not None:
            self.ffmpeg.stdin.close()
            await self.ffmpeg.stdin.wait_closed()
        await self.pump_task
        await self.upstream.send(json.dumps({"is_speaking": False}))

        try:
            await asyncio.wait_for(
                self.final_event.wait(),
                timeout=settings.funasr_final_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("FunASR final result timed out; using accumulated online text")
            await self.update_queue.put(
                StreamingRecognitionUpdate(text=self.transcript.current_text, is_final=True)
            )
            self.final_event.set()

    async def receive_update(self) -> StreamingRecognitionUpdate:
        return await self.update_queue.get()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for task in (self.pump_task, self.receive_task):
            if not task.done():
                task.cancel()
        if self.ffmpeg.stdin is not None and not self.ffmpeg.stdin.is_closing():
            self.ffmpeg.stdin.close()
        if self.ffmpeg.returncode is None:
            self.ffmpeg.terminate()
            try:
                await asyncio.wait_for(self.ffmpeg.wait(), timeout=2)
            except TimeoutError:
                self.ffmpeg.kill()
                await self.ffmpeg.wait()
        if not self.stderr_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.stderr_task), timeout=2)
            except TimeoutError:
                self.stderr_task.cancel()
        await self.upstream.close()

    async def _pump_pcm_to_funasr(self) -> None:
        if self.ffmpeg.stdout is None:
            raise RuntimeError("FFmpeg output is unavailable")

        buffer = bytearray()
        while True:
            chunk = await self.ffmpeg.stdout.read(FUNASR_PCM_CHUNK_BYTES)
            if not chunk:
                break
            buffer.extend(chunk)
            while len(buffer) >= FUNASR_PCM_CHUNK_BYTES:
                await self.upstream.send(bytes(buffer[:FUNASR_PCM_CHUNK_BYTES]))
                del buffer[:FUNASR_PCM_CHUNK_BYTES]
        if buffer:
            await self.upstream.send(bytes(buffer))

        return_code = await self.ffmpeg.wait()
        error_output = await self.stderr_task
        if return_code != 0:
            logger.warning(
                "FFmpeg MP3 decoder failed return_code=%s detail=%s",
                return_code,
                error_output[-500:],
            )
            raise RuntimeError("Unable to decode streaming audio")

    async def _read_ffmpeg_errors(self) -> bytes:
        if self.ffmpeg.stderr is None:
            return b""
        return await self.ffmpeg.stderr.read()

    async def _receive_funasr_updates(self) -> None:
        try:
            async for raw_message in self.upstream:
                if isinstance(raw_message, bytes):
                    continue
                payload = json.loads(raw_message)
                update = self.transcript.apply(payload)
                if update is None:
                    continue
                await self.update_queue.put(update)
                if update.is_final:
                    self.final_event.set()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("FunASR result stream failed")
            if not self.final_event.is_set():
                await self.update_queue.put(
                    StreamingRecognitionUpdate(text=self.transcript.current_text, is_final=True)
                )
                self.final_event.set()


class FunASRStreamingVoiceRecognizer(VoiceStreamingRecognizer):
    async def open_session(self) -> VoiceStreamingRecognitionSession:
        from websockets.asyncio.client import connect

        upstream = await connect(
            settings.funasr_ws_url,
            open_timeout=10,
            close_timeout=3,
            max_size=settings.voice_upload_max_bytes,
        )
        try:
            ffmpeg = await asyncio.create_subprocess_exec(
                settings.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "mp3",
                "-i",
                "pipe:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:
            await upstream.close()
            raise

        await upstream.send(
            json.dumps(
                {
                    "mode": settings.funasr_mode,
                    "chunk_size": [5, 10, 5],
                    "chunk_interval": 10,
                    "audio_fs": 16000,
                    "wav_name": f"echo-{uuid4().hex}",
                    "wav_format": "pcm",
                    "is_speaking": True,
                    "hotwords": "",
                    "itn": True,
                }
            )
        )
        return FunASRStreamingRecognitionSession(upstream=upstream, ffmpeg=ffmpeg)
