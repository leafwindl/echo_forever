from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    ChatHistoryMessage,
    ChatQueueFullError,
    ChatRequestInProgressError,
    ChatValidationError,
)
from features.chat.infrastructure.container import get_async_chat_repository
from features.chat.infrastructure.events import ChatEvent, get_chat_event_broker
from features.chat.interface.schemas import (
    AsyncChatMessageRequest,
    ChatAcceptedTurnResponse,
    ChatContentPart,
    ChatHistoryMessageResponse,
    ChatHistoryResponse,
    ChatMessageAcceptedResponse,
    ChatRequest,
    ChatResponse,
    ChatSource,
    ClearChatResponse,
)
from features.chat.public import (
    accept_chat_message,
    clear_chat_context,
    list_chat_messages,
    send_chat_message,
)
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
sticker_repository = PostgresStickerRepository()


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


def _history_message_response(item: ChatHistoryMessage) -> ChatHistoryMessageResponse:
    return ChatHistoryMessageResponse(
        message_id=item.message_id,
        stable_message_id=item.stable_message_id,
        client_message_id=item.client_message_id,
        role=item.role,
        message_type=item.message_type,
        content=item.content,
        content_parts=[ChatContentPart(**vars(part)) for part in item.content_parts],
        sources=[ChatSource(**vars(source)) for source in item.sources],
        agent_turn_id=item.agent_turn_id,
        reply_group_id=item.reply_group_id,
        sequence_in_group=item.sequence_in_group,
        in_reply_to_message_id=item.in_reply_to_message_id,
        created_at=item.created_at,
    )


def _history_message_payload(item: ChatHistoryMessage) -> dict[str, object]:
    return _history_message_response(item).model_dump(mode="json")


def _encode_sse(event: ChatEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {payload}\n\n"


@router.get("/messages", response_model=ChatHistoryResponse)
def chat_messages(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    before_id: int | None = Query(default=None, ge=1),
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
):
    try:
        page = list_chat_messages(
            current_user.user_id,
            before_id=before_id,
            after_id=after_id,
            limit=limit,
        )
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChatHistoryResponse(
        conversation_id=page.conversation_id,
        items=[_history_message_response(item) for item in page.items],
        has_more=page.has_more,
        next_before_id=page.next_before_id,
        next_after_id=page.next_after_id,
    )


@router.post(
    "/messages",
    response_model=ChatMessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def accept_message(
    body: AsyncChatMessageRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    try:
        consume_chat_quota(current_user.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="消息发送过于频繁，请稍后再试",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    content_parts: tuple[ContentPart, ...] = ()
    if body.message_type == "sticker":
        sticker = sticker_repository.get(current_user.user_id, body.sticker_id.strip())
        if sticker is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="表情包不存在或无权使用",
            )
        content_parts = (
            ContentPart(type="sticker", sticker_id=sticker.sticker_id, url=sticker.url),
        )

    try:
        result = accept_chat_message(
            user_id=current_user.user_id,
            client_message_id=str(body.client_message_id),
            message_type=body.message_type,
            text=body.text,
            content_parts=content_parts,
        )
    except ChatQueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="待处理消息较多，请稍后再发",
            headers={"Retry-After": "2"},
        ) from exc
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ChatMessageAcceptedResponse(
        conversation_id=result.conversation_id,
        message=_history_message_response(result.message),
        turn=ChatAcceptedTurnResponse(
            turn_id=result.turn.turn_id,
            status=result.turn.status.value,
        ),
        replayed=result.replayed,
    )


@router.get("/events")
async def chat_events(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    after_message_id: int = Query(default=0, ge=0),
):
    user_id = current_user.user_id
    broker = get_chat_event_broker()
    repository = get_async_chat_repository()

    async def stream() -> AsyncIterator[str]:
        async with broker.subscribe(user_id) as queue:
            initial = list_chat_messages(user_id, after_id=after_message_id, limit=50)
            yield _encode_sse(
                ChatEvent(
                    event="chat.ready",
                    data={
                        "conversation_id": initial.conversation_id,
                        "after_message_id": after_message_id,
                        "echo_typing": repository.has_running_turn(
                            user_id,
                            initial.conversation_id,
                        ),
                    },
                )
            )

            cursor = after_message_id
            page = initial
            while True:
                if page.items:
                    cursor = page.items[-1].message_id
                    yield _encode_sse(
                        ChatEvent(
                            event="chat.sync",
                            data={
                                "conversation_id": page.conversation_id,
                                "messages": [
                                    _history_message_payload(item) for item in page.items
                                ],
                            },
                        )
                    )
                if not page.has_more:
                    break
                page = list_chat_messages(user_id, after_id=cursor, limit=50)

            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=settings.chat_sse_heartbeat_seconds,
                    )
                except TimeoutError:
                    event = ChatEvent(
                        event="chat.heartbeat",
                        data={"conversation_id": initial.conversation_id},
                    )
                yield _encode_sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/send", response_model=ChatResponse)
async def call_send(
    body: ChatRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Synchronous Agent + TTS delivery used only by voice calls."""
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
            message=body.message.strip(),
            conversation_mode="call",
            request_id=request.headers.get("X-Request-ID", "")[:80],
        )
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ChatRequestInProgressError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Voice call chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="内部服务器错误",
        ) from exc

    return ChatResponse(
        reply=result.reply,
        audio_urls=list(result.audio_urls),
        content_parts=[ChatContentPart(**vars(part)) for part in result.content_parts],
        sources=[ChatSource(**vars(source)) for source in result.sources],
    )


@router.post("/clear", response_model=ClearChatResponse)
async def chat_clear(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Clear chat messages and cancel unfinished turns without touching long-term memory."""
    try:
        result = clear_chat_context(current_user.user_id)
        page = list_chat_messages(current_user.user_id, limit=1)
        await get_chat_event_broker().publish(
            current_user.user_id,
            ChatEvent(
                event="chat.conversation.reset",
                data={"conversation_id": page.conversation_id},
            ),
        )
    except ChatValidationError as exc:
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
