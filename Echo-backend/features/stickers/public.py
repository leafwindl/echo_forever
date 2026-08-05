from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository
from features.stickers.infrastructure.container import get_sticker_generator


def search_stickers(user_id: str, intent: str, limit: int = 3):
    return PostgresStickerRepository().list(user_id, intent, limit)


def send_sticker(user_id: str, sticker_id: str):
    """Validate an available sticker before the Agent attaches it to a reply."""
    clean_id = sticker_id.strip()
    if not clean_id:
        return None
    return PostgresStickerRepository().get(user_id, clean_id)


async def generate_pending_stickers() -> int:
    return await get_sticker_generator().execute()


__all__ = ["generate_pending_stickers", "search_stickers", "send_sticker"]
