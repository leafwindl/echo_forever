import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from features.voice.interface.schemas import VoiceASRResponse
from features.voice.public import UnsupportedVoiceFormatError, recognize_voice

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
