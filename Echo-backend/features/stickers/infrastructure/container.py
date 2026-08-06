from functools import lru_cache
from pathlib import Path

from providers.image_generation_provider import OpenAICompatibleImageGenerationProvider
from shared.config import settings

from features.stickers.application.generate_stickers import GeneratePendingStickers
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository


@lru_cache(maxsize=1)
def get_sticker_generator() -> GeneratePendingStickers:
    static_root = Path(__file__).resolve().parents[3] / "static" / "stickers"
    return GeneratePendingStickers(
        PostgresStickerRepository(),
        OpenAICompatibleImageGenerationProvider(),
        static_root,
        settings.sticker_upload_max_bytes,
        settings.static_url_prefix,
    )
