import asyncio
import json
import logging
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.admin.public import AdminValidationError, clear_user_chat_context
from features.chat.interface.schemas import ChatRequest, ChatResponse, ClearChatResponse
from features.chat.public import (
    ChatRequestInProgressError,
    ChatValidationError,
    send_chat_message,
    stream_chat_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def consume_chat_quota(user_id: str) -> None:
    request_limiter.consume(
        [
            RateLimitRule(
                key=f"chat:user:{user_id}",
                requests=settings.chat_rate_limit_requests,
                window_seconds=settings.chat_rate_limit_window_seconds,
                daily_requests=settings.chat_daily_request_limit,
            ),
            RateLimitRule(
                key="chat:global",
                daily_requests=settings.global_daily_chat_request_limit,
            ),
        ]
    )


def encode_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/send", response_model=ChatResponse)
async def chat_send(
    request: ChatRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """发送用户消息并获取 AI 回复，按需附带语音回复。"""
    try:
        consume_chat_quota(current_user.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="消息发送过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        result = await send_chat_message(
            user_id=current_user.user_id,
            message=request.message,
            input_type=request.input_type,
            voice_reply_enabled=request.voice_reply_enabled,
        )
    except ChatValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ChatRequestInProgressError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        logger.exception("Text chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="内部服务器错误",
        ) from e

    return ChatResponse(
        reply=result.reply,
        audio_url=result.audio_url,
        audio_urls=list(result.audio_urls),
    )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Stream text deltas and ready-to-play speech segments as SSE events."""
    try:
        consume_chat_quota(current_user.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="消息发送过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    async def event_stream():
        event_queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_text_delta(delta: str) -> None:
            await event_queue.put(("delta", {"text": delta}))

        async def on_audio_ready(audio_url: str) -> None:
            await event_queue.put(("audio", {"url": audio_url}))

        async def produce_reply() -> None:
            try:
                result = await stream_chat_message(
                    user_id=current_user.user_id,
                    message=request.message,
                    input_type=request.input_type,
                    voice_reply_enabled=request.voice_reply_enabled,
                    on_text_delta=on_text_delta,
                    on_audio_ready=on_audio_ready,
                )
                await event_queue.put(
                    (
                        "done",
                        {
                            "reply": result.reply,
                            "audio_url": result.audio_url,
                            "audio_urls": list(result.audio_urls),
                        },
                    )
                )
            except ChatRequestInProgressError as exc:
                await event_queue.put(
                    ("error", {"detail": str(exc), "code": "request_in_progress"})
                )
            except ChatValidationError as exc:
                await event_queue.put(("error", {"detail": str(exc), "code": "validation"}))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Streaming chat failed")
                await event_queue.put(
                    ("error", {"detail": "内部服务器错误", "code": "internal"})
                )
            finally:
                await event_queue.put(None)

        producer_task = asyncio.create_task(produce_reply())
        try:
            yield encode_sse_event("ready", {})
            while True:
                item = await event_queue.get()
                if item is None:
                    return
                event, data = item
                yield encode_sse_event(event, data)
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/clear", response_model=ClearChatResponse)
async def chat_clear(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """清除当前登录用户的聊天记录和会话摘要，不影响长期记忆。"""
    try:
        result = clear_user_chat_context(current_user.user_id)
    except AdminValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to clear chat context for user_id=%s", current_user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="清除聊天上下文失败",
        ) from exc
    return ClearChatResponse(
        deleted_messages=result.deleted_messages,
        reset_conversations=result.reset_conversations,
    )
