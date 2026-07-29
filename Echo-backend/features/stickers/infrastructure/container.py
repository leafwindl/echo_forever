from functools import lru_cache
from pathlib import Path

from features.stickers.application.generate_stickers import GeneratePendingStickers
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository
from providers.image_generation_provider import OpenAICompatibleImageGenerationProvider


@lru_cache(maxsize=1)
def get_sticker_generator() -> GeneratePendingStickers:
    static_root = Path(__file__).resolve().parents[3] / "static" / "stickers"
    return GeneratePendingStickers(
        PostgresStickerRepository(), OpenAICompatibleImageGenerationProvider(), static_root
    )
