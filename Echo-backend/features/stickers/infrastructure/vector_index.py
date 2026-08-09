from __future__ import annotations

import logging

from providers.embedding_provider import get_embedding_provider
from shared.config import settings

from features.stickers.domain.entities import Sticker
from features.stickers.domain.services import (
    build_sticker_query_text,
    build_sticker_semantic_text,
)
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository

logger = logging.getLogger(__name__)


async def upsert_sticker_embedding(sticker: Sticker) -> bool:
    semantic_text = build_sticker_semantic_text(
        sticker.description,
        sticker.semantic_tags,
    )
    if not semantic_text or not settings.sticker_vector_search_enabled:
        return False
    embedding = await get_embedding_provider().create_embedding(
        semantic_text,
        model=settings.embedding_model,
    )
    PostgresStickerRepository().upsert_embedding(
        sticker.sticker_id,
        settings.embedding_model,
        semantic_text,
        embedding,
    )
    logger.info(
        "Sticker embedding upserted sticker_id=%s owner_type=%s",
        sticker.sticker_id,
        sticker.owner_type,
    )
    return True


async def safe_upsert_sticker_embedding(sticker: Sticker) -> bool:
    try:
        return await upsert_sticker_embedding(sticker)
    except Exception as exc:
        logger.warning(
            "Sticker embedding skipped sticker_id=%s error=%s",
            sticker.sticker_id,
            type(exc).__name__,
        )
        return False


async def backfill_sticker_embeddings(limit: int | None = None) -> int:
    if not settings.sticker_vector_search_enabled or not settings.embedding_api_key:
        return 0
    repository = PostgresStickerRepository()
    stickers = repository.list_active_for_embedding(
        limit or settings.sticker_embedding_backfill_limit
    )
    existing = repository.list_embedding_metadata(settings.embedding_model)
    completed = 0
    for sticker in stickers:
        semantic_text = build_sticker_semantic_text(
            sticker.description,
            sticker.semantic_tags,
        )
        if not semantic_text or existing.get(sticker.sticker_id) == semantic_text:
            continue
        if await safe_upsert_sticker_embedding(sticker):
            completed += 1
    if completed:
        logger.info("Sticker embedding backfill completed count=%s", completed)
    return completed


async def search_sticker_embeddings(
    user_id: str,
    query: str,
    limit: int,
    *,
    conversation_id: str | None = None,
    purpose: str = "explicit_request",
) -> list[Sticker]:
    repository = PostgresStickerRepository()
    clean_query = query.strip()
    if (
        not clean_query
        or not settings.sticker_vector_search_enabled
        or not settings.embedding_api_key
    ):
        return repository.list(
            user_id,
            clean_query,
            limit,
            conversation_id=conversation_id,
            purpose=purpose,
        )

    try:
        query_embedding = await get_embedding_provider().create_embedding(
            build_sticker_query_text(clean_query),
            model=settings.embedding_model,
        )
        matches = repository.list_vector_matches(
            user_id,
            clean_query,
            query_embedding,
            settings.embedding_model,
            settings.sticker_vector_top_k,
            conversation_id=conversation_id,
            purpose=purpose,
            score_threshold=settings.sticker_vector_score_threshold,
            maximum_score_gap=settings.sticker_vector_max_score_gap,
        )
    except Exception as exc:
        logger.warning(
            "Sticker vector search unavailable user_id=%s error=%s",
            user_id,
            type(exc).__name__,
        )
        matches = []

    if matches:
        return matches[:limit]
    return repository.list(
        user_id,
        clean_query,
        limit,
        conversation_id=conversation_id,
        purpose=purpose,
    )
