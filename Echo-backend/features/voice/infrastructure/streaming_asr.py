import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import suppress
from typing import Any
from urllib.parse import quote, urlencode
from uuid import uuid4

from shared.config import settings

from features.voice.domain.entities import StreamingRecognitionUpdate
from features.voice.domain.services import (
    VoiceStreamingRecognitionSession,
    VoiceStreamingRecognizer,
)

logger = logging.getLogger(__name__)

TENCENT_ASR_HOST = "asr.cloud.tencent.com"
TENCENT_ASR_PATH_PREFIX = "/asr/v2"


class TencentASRTranscriptAccumulator:
    """Merge Tencent's mutable sentence slices into one current transcript."""

    def __init__(self) -> None:
        self.stable_segments: dict[int, str] = {}
        self.pending_segments: dict[int, str] = {}

    @property
    def current_text(self) -> str:
        indexes = sorted(set(self.stable_segments) | set(self.pending_segments))
        return "".join(
            self.pending_segments.get(index, self.stable_segments.get(index, ""))
            for index in indexes
        ).strip()

    def apply(self, payload: dict[str, Any]) -> StreamingRecognitionUpdate | None:
        is_final = int(payload.get("final") or 0) == 1
        result = payload.get("result")
        if not isinstance(result, dict):
            return (
                StreamingRecognitionUpdate(text=self.current_text, is_final=True)
                if is_final
                else None
            )

        index = int(result.get("index") or 0)
        slice_type = int(result.get("slice_type") or 0)
        text = str(result.get("voice_text_str") or "")
        if slice_type == 2:
            self.stable_segments[index] = text
            self.pending_segments.pop(index, None)
        else:
            self.pending_segments[index] = text

        return StreamingRecognitionUpdate(text=self.current_text, is_final=is_final)


class TencentASRStreamingRecognitionSession(VoiceStreamingRecognitionSession):
    def __init__(self, upstream: Any):
        self.upstream = upstream
        self.update_queue: asyncio.Queue[StreamingRecognitionUpdate] = asyncio.Queue()
        self.final_event = asyncio.Event()
        self.transcript = TencentASRTranscriptAccumulator()
        self.finished = False
        self.closed = False
        self.failed = False
        self.receive_task = asyncio.create_task(self._receive_updates())

    async def send_audio(self, audio_bytes: bytes) -> None:
        if self.finished or self.closed:
            raise RuntimeError("Streaming ASR session is no longer accepting audio")
        if audio_bytes:
            await self.upstream.send(audio_bytes)

    async def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        await self.upstream.send(json.dumps({"type": "end"}))
        try:
            await asyncio.wait_for(
                self.final_event.wait(),
                timeout=settings.tencent_asr_final_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("Tencent ASR final result timed out")
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
        if not self.receive_task.done():
            self.receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.receive_task
        await self.upstream.close()

    async def _receive_updates(self) -> None:
        try:
            async for raw_message in self.upstream:
                if isinstance(raw_message, bytes):
                    continue
                payload = json.loads(raw_message)
                code = int(payload.get("code") or 0)
                if code != 0:
                    raise RuntimeError(f"Tencent ASR error code={code}")
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
            self.failed = True
            logger.exception("Tencent ASR result stream failed")
            if not self.final_event.is_set():
                await self.update_queue.put(
                    StreamingRecognitionUpdate(text=self.transcript.current_text, is_final=True)
                )
                self.final_event.set()


def build_tencent_asr_websocket_url(voice_id: str, now: int | None = None) -> str:
    if not settings.tencent_app_id:
        raise ValueError("TENCENT_APP_ID is required for streaming ASR")
    if not settings.tencent_secret_id or not settings.tencent_secret_key:
        raise ValueError("Tencent credentials are required for streaming ASR")

    timestamp = int(time.time()) if now is None else now
    path = f"{TENCENT_ASR_PATH_PREFIX}/{settings.tencent_app_id}"
    params = {
        "convert_num_mode": 1,
        "engine_model_type": settings.tencent_asr_engine_model_type,
        "expired": timestamp + 3600,
        "filter_empty_result": 1,
        "filter_modal": 0,
        "filter_punc": 0,
        "needvad": 1,
        "nonce": secrets.randbelow(2_000_000_000) + 1,
        "secretid": settings.tencent_secret_id,
        "timestamp": timestamp,
        "vad_silence_time": 800,
        "voice_format": 1,
        "voice_id": voice_id,
    }
    query = urlencode(sorted(params.items()))
    signature_source = f"{TENCENT_ASR_HOST}{path}?{query}"
    digest = hmac.new(
        settings.tencent_secret_key.encode("utf-8"),
        signature_source.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = quote(base64.b64encode(digest).decode("ascii"), safe="")
    return f"wss://{signature_source}&signature={signature}"


class TencentASRStreamingVoiceRecognizer(VoiceStreamingRecognizer):
    async def open_session(self) -> VoiceStreamingRecognitionSession:
        from websockets.asyncio.client import connect

        voice_id = uuid4().hex
        upstream = await connect(
            build_tencent_asr_websocket_url(voice_id),
            open_timeout=10,
            close_timeout=3,
            max_size=settings.voice_upload_max_bytes,
        )
        try:
            raw_handshake = await asyncio.wait_for(upstream.recv(), timeout=10)
            if isinstance(raw_handshake, bytes):
                raise RuntimeError("Tencent ASR returned an invalid handshake")
            handshake = json.loads(raw_handshake)
            if int(handshake.get("code") or 0) != 0:
                raise RuntimeError(f"Tencent ASR handshake failed code={handshake.get('code')}")
        except Exception:
            await upstream.close()
            raise
        return TencentASRStreamingRecognitionSession(upstream=upstream)
