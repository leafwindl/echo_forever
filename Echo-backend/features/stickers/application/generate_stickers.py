from __future__ import annotations

import logging
import uuid
from pathlib import Path

from features.stickers.domain.repositories import StickerGenerationRepository
from features.stickers.domain.services import ImageGenerator, validate_image

logger = logging.getLogger(__name__)


class GeneratePendingStickers:
    def __init__(
        self,
        repository: StickerGenerationRepository,
        provider: ImageGenerator,
        static_root: Path,
        maximum_bytes: int,
        static_url_prefix: str,
    ):
        self.repository = repository
        self.provider = provider
        self.static_root = static_root
        self.maximum_bytes = maximum_bytes
        self.static_url_prefix = static_url_prefix

    async def execute(self) -> int:
        completed = 0
        for job in self.repository.claim_generation_jobs(limit=3):
            try:
                prompt = (
                    "生成一张适合聊天发送的原创表情包，主体明确、构图简洁、不要品牌或真人肖像。"
                    + job["prompt"]
                )
                content, content_type = await self.provider.generate(prompt)
                content_hash = validate_image(content, content_type, self.maximum_bytes)
                self.static_root.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid.uuid4().hex}.png"
                (self.static_root / filename).write_bytes(content)
                self.repository.complete_generation(
                    job["job_id"],
                    job["user_id"],
                    f"stickers/{filename}",
                    f"{self.static_url_prefix.rstrip('/')}/static/stickers/{filename}",
                    content_type,
                    len(content),
                    content_hash,
                    job["normalized_intent"],
                )
                completed += 1
            except Exception as exc:
                logger.warning("Sticker generation failed job_id=%s", job["job_id"], exc_info=True)
                self.repository.fail_generation(job["job_id"], type(exc).__name__)
        return completed
