from features.stickers.infrastructure.container import get_sticker_generator
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository
from features.stickers.infrastructure.urls import resolve_sticker_url
from features.stickers.infrastructure.vector_index import (
    backfill_sticker_embeddings,
    safe_upsert_sticker_embedding,
    search_sticker_embeddings,
)


async def search_stickers(
    user_id: str,
    intent: str,
    limit: int = 3,
):
    return await search_sticker_embeddings(
        user_id,
        intent,
        limit,
    )


def send_sticker(user_id: str, sticker_id: str):
    """Validate an available sticker before the Agent attaches it to a reply."""
    clean_id = sticker_id.strip()
    if not clean_id:
        return None
    return PostgresStickerRepository().get(user_id, clean_id)


async def generate_pending_stickers() -> int:
    return await get_sticker_generator().execute()


def resolve_sticker_asset_url(
    *,
    source: str,
    storage_key: str,
    public_url: str,
) -> str:
    return resolve_sticker_url(
        source=source,
        storage_key=storage_key,
        public_url=public_url,
    )


__all__ = [
    "backfill_sticker_embeddings",
    "generate_pending_stickers",
    "resolve_sticker_asset_url",
    "safe_upsert_sticker_embedding",
    "search_stickers",
    "send_sticker",
]
