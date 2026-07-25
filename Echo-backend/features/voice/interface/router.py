import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from features.voice.interface.schemas import VoiceASRResponse
from features.voice.public import UnsupportedVoiceFormatError, recognize_voice
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


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
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="语音文件过大",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/asr", response_model=VoiceASRResponse)
async def voice_asr(
    audio: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        request_limiter.consume(
            [
                RateLimitRule(
                    key=f"voice:user:{current_user.user_id}",
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
    except UnsupportedVoiceFormatError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Voice ASR failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="语音识别失败") from e
