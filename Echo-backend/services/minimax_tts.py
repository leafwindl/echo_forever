import httpx
import os
import edge_tts
from config import settings
from fastapi import HTTPException

async def text_to_speech(text: str, voice_id: str = "zh-CN-XiaoxiaoNeural") -> bytes:
    """
    使用完全免费的 Edge TTS 生成语音。
    不需要任何 API Key！
    默认使用微软晓晓（zh-CN-XiaoxiaoNeural）的高质量女声。
    """
    if not text:
        raise ValueError("TTS text cannot be empty")
        
    try:
        communicate = edge_tts.Communicate(text, voice_id)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Edge TTS error: {str(e)}")
