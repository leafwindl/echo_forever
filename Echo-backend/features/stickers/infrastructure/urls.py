from __future__ import annotations

import logging

from shared.config import settings
from shared.storage import get_cos_object_storage

logger = logging.getLogger(__name__)


def resolve_sticker_url(
    *,
    source: str,
    storage_key: str,
    public_url: str,
) -> str:
    if source != "builtin" or not storage_key or not settings.cos_enabled:
        return public_url
    try:
        return get_cos_object_storage().download_url(storage_key)
    except Exception:
        logger.warning("Failed to sign COS sticker URL storage_key=%s", storage_key, exc_info=True)
        return public_url
