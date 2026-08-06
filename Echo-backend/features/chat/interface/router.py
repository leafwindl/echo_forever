import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.agent.domain.entities import ContentPart
from features.chat.interface.schemas import (
    ChatContentPart,
    ChatHistoryMessageResponse,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    ChatSource,
    ClearChatResponse,
)
from features.chat.public import (
    ChatRequestInProgressError,
    ChatValidationError,
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


@router.get("/messages", response_model=ChatHistoryResponse)
def chat_messages(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
):
    page = list_chat_messages(current_user.user_id, before_id=before_id, limit=limit)
    return ChatHistoryResponse(
        conversation_id=page.conversation_id,
        items=[
            ChatHistoryMessageResponse(
                message_id=item.message_id,
                role=item.role,
                message_type=item.message_type,
                content=item.content,
                content_parts=[ChatContentPart(**vars(part)) for part in item.content_parts],
                created_at=item.created_at,
            )
            for item in page.items
        ],
        has_more=page.has_more,
        next_before_id=page.next_before_id,
    )


@router.post("/send", response_model=ChatResponse)
async def chat_send(
    body: ChatRequest,
    request: Request,
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

    message = body.message.strip()
    user_message_type = "text"
    sticker_intent = ""
    user_content_parts: tuple[ContentPart, ...] = ()
    if body.content_parts:
        sticker_id = body.content_parts[0].sticker_id.strip()
        sticker = sticker_repository.get(current_user.user_id, sticker_id)
        if sticker is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="表情包不存在或无权使用",
            )
        tags = "、".join(sticker.semantic_tags)
        sticker_intent = " ".join(
            part for part in (sticker.description, *sticker.semantic_tags) if part.strip()
        )
        message = (
            f"用户发送了一张表情包。描述：{sticker.description}。语义标签：{tags or '未提供'}。"
        )
        user_message_type = "sticker"
        user_content_parts = (
            ContentPart(type="sticker", sticker_id=sticker.sticker_id, url=sticker.url),
        )

    try:
        result = await send_chat_message(
            user_id=current_user.user_id,
            message=message,
            conversation_mode=body.mode,
            user_message_type=user_message_type,
            sticker_intent=sticker_intent,
            user_content_parts=user_content_parts,
            request_id=request.headers.get("X-Request-ID", "")[:80],
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
        audio_urls=list(result.audio_urls),
        content_parts=[ChatContentPart(**vars(part)) for part in result.content_parts],
        sources=[ChatSource(**vars(source)) for source in result.sources],
    )


@router.post("/clear", response_model=ClearChatResponse)
async def chat_clear(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """清除当前登录用户的聊天记录和会话摘要，不影响长期记忆。"""
    try:
        result = clear_chat_context(current_user.user_id)
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
