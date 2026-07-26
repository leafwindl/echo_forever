import asyncio
import json
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from shared.config import settings
from shared.interface.dependencies import (
    CurrentUser,
    get_current_user,
    resolve_current_user_from_token,
)
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.voice.interface.schemas import VoiceASRResponse
from features.voice.public import (
    UnsupportedVoiceFormatError,
    open_streaming_voice_recognition,
    recognize_voice,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


def consume_voice_quota(user_id: str) -> None:
    request_limiter.consume(
        [
            RateLimitRule(
                key=f"voice:user:{user_id}",
                requests=settings.voice_rate_limit_requests,
                window_seconds=settings.voice_rate_limit_window_seconds,
                daily_requests=settings.voice_daily_request_limit,
            ),
            RateLimitRule(
                key="voice:global",
                daily_requests=settings.global_daily_voice_request_limit,
            ),
        ]
    )


async def read_upload_with_limit(audio: UploadFile, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("Voice upload limit must be positive")

    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await audio.read(min(64 * 1024, max_bytes - total_bytes + 1))
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="语音文件过大",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/asr", response_model=VoiceASRResponse)
async def voice_asr(
    audio: Annotated[UploadFile, File()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    try:
        consume_voice_quota(current_user.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="语音请求过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        result = await recognize_voice(
            audio_bytes=await read_upload_with_limit(audio, settings.voice_upload_max_bytes),
            content_type=audio.content_type or "",
        )
        return VoiceASRResponse(user_text=result.user_text)
    except HTTPException:
        raise
    except UnsupportedVoiceFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Voice ASR failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="语音识别失败",
        ) from exc


@router.websocket("/asr/stream")
async def voice_asr_stream(websocket: WebSocket):
    if not settings.voice_streaming_asr_enabled:
        await websocket.close(code=4404, reason="Streaming ASR is disabled")
        return

    try:
        current_user = resolve_current_user_from_token(websocket.headers.get("authorization"))
        if current_user is None:
            await websocket.close(code=4401, reason="Missing access token")
            return
        consume_voice_quota(current_user.user_id)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid access token")
        return
    except RateLimitExceeded:
        await websocket.close(code=4429, reason="Voice request limit exceeded")
        return

    await websocket.accept()
    session = None
    sender_task: asyncio.Task[None] | None = None
    total_audio_bytes = 0

    async def send_recognition_updates() -> None:
        if session is None:
            return
        while True:
            update = await session.receive_update()
            await websocket.send_json(
                {
                    "type": "final" if update.is_final else "partial",
                    "text": update.text,
                }
            )
            if update.is_final:
                return

    try:
        session = await open_streaming_voice_recognition()
        sender_task = asyncio.create_task(send_recognition_updates())
        await websocket.send_json({"type": "ready"})

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            audio_bytes = message.get("bytes")
            if audio_bytes is not None:
                total_audio_bytes += len(audio_bytes)
                if total_audio_bytes > settings.voice_upload_max_bytes:
                    await websocket.send_json(
                        {"type": "error", "detail": "Voice audio exceeds configured size limit"}
                    )
                    await websocket.close(code=1009)
                    break
                await session.send_audio(audio_bytes)
                continue

            raw_text = message.get("text")
            if raw_text is None:
                continue
            try:
                event = str(json.loads(raw_text).get("event") or "")
            except (json.JSONDecodeError, AttributeError):
                continue

            if event == "stop":
                await session.finish()
                if sender_task is not None:
                    await asyncio.wait_for(
                        sender_task,
                        timeout=settings.funasr_final_timeout_seconds + 2,
                    )
                await websocket.close(code=1000)
                return
            if event == "cancel":
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Streaming voice ASR failed")
        try:
            await websocket.send_json({"type": "error", "detail": "Streaming ASR failed"})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if sender_task is not None and not sender_task.done():
            sender_task.cancel()
        if session is not None:
            await session.close()
