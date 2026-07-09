import logging

from fastapi import APIRouter, Depends, HTTPException, status

from features.chat.interface.schemas import ChatRequest, ChatResponse
from features.chat.public import ChatRequestInProgressError, ChatValidationError, send_chat_message
from shared.interface.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatResponse)
async def chat_send(request: ChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """发送用户消息并获取 AI 回复，按需附带语音回复。"""
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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except Exception as e:
        logger.exception("Text chat failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误") from e

    return ChatResponse(reply=result.reply, audio_url=result.audio_url)
