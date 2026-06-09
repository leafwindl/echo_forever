import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from features.chat.public import ChatValidationError
from features.voice.interface.schemas import VoiceASRResponse, VoiceReplyRequest, VoiceReplyResponse
from features.voice.public import UnsupportedVoiceFormatError, generate_voice_reply, recognize_voice
from shared.interface.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/asr", response_model=VoiceASRResponse)
async def voice_asr(audio: UploadFile = File(...)):
    """仅执行语音识别 (ASR)，返回用户说的话。"""
    try:
        result = await recognize_voice(
            audio_bytes=await audio.read(),
            content_type=audio.content_type or "",
        )
        return VoiceASRResponse(user_text=result.user_text)
    except UnsupportedVoiceFormatError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Voice ASR failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.post("/reply", response_model=VoiceReplyResponse)
async def voice_reply(
    request: VoiceReplyRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """接收用户的文字，调用 LLM 和 TTS，返回 AI 的文字和语音。"""
    try:
        result = await generate_voice_reply(
            user_id=current_user.user_id,
            message=request.message,
        )
        return VoiceReplyResponse(reply=result.reply, audio_url=result.audio_url)
    except ChatValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Voice reply failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Voice reply failed") from e
