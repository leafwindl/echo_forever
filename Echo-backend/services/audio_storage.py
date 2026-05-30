import os
import uuid
from pathlib import Path
from config import settings

STATIC_VOICE_DIR = Path("static/voices")
STATIC_VOICE_DIR.mkdir(parents=True, exist_ok=True)

async def save_audio_file(audio_bytes: bytes) -> str:
    """
    保存音频字节流到静态目录，返回可访问的 URL。
    """
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = STATIC_VOICE_DIR / filename
    with open(filepath, "wb") as f:
        f.write(audio_bytes)
    # 返回 URL，注意静态路径挂载为 /static
    url = f"{settings.static_url_prefix}/static/voices/{filename}"
    return url