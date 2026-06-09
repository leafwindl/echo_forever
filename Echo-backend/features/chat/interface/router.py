import logging

from fastapi import APIRouter, Depends, HTTPException, status

from features.chat.interface.schemas import ChatRequest, ChatResponse
from features.chat.public import ChatValidationError, generate_chat_reply
from shared.interface.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatResponse)
async def chat_send(request: ChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """发送文本消息并获取 AI 回复。"""
    try:
        result = await generate_chat_reply(
            user_id=current_user.user_id,
            message=request.message,
            user_message_type="text",
            assistant_message_type="text",
        )
    except ChatValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except Exception as e:
        logger.exception("Text chat failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="内部服务器错误") from e

    return ChatResponse(reply=result.reply)
