import uuid
from pathlib import Path

from shared.config import settings

BASE_DIR = Path(__file__).resolve().parents[3]
STATIC_VOICE_DIR = BASE_DIR / "static" / "voices"


def get_voice_storage_dir() -> Path:
    STATIC_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    return STATIC_VOICE_DIR


async def save_audio_file(audio_bytes: bytes) -> str:
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = get_voice_storage_dir() / filename
    filepath.write_bytes(audio_bytes)
    return f"{settings.static_url_prefix}/static/voices/{filename}"
