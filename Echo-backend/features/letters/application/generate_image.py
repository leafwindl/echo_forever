from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from features.letters.domain.services import LetterImageGenerator, LetterImageStorage
from features.stickers.domain.services import validate_image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LetterImageResult:
    storage_key: str = ""
    content_type: str = ""
    byte_size: int = 0
    provider: str = ""
    model: str = ""
    reference_version: str = ""
    width: int | None = None
    height: int | None = None
    status: str = "disabled"
    failure_code: str | None = None


@dataclass(frozen=True)
class LetterImagePolicy:
    enabled: bool
    aspect_ratio: str
    maximum_attempts: int
    maximum_bytes: int
    timeout_seconds: int
    provider_name: str
    model: str
    reference_version: str
    reference_storage_key: str = ""


class GenerateLetterImage:
    def __init__(
        self,
        provider: LetterImageGenerator,
        storage: LetterImageStorage | None,
        policy: LetterImagePolicy,
        clock: Callable[[], datetime] | None = None,
    ):
        self.provider = provider
        self.storage = storage
        self.policy = policy
        self.clock = clock or _utc_now

    async def execute(
        self,
        *,
        user_id: str,
        local_date: str,
        letter_id: str,
        image_brief: dict[str, object],
        deadline: datetime | None = None,
    ) -> LetterImageResult:
        if not self.policy.enabled:
            return LetterImageResult()
        if self.storage is None:
            return LetterImageResult(status="failed", failure_code="cos_unavailable")
        reference_images = _signed_reference_url(
            self.storage,
            self.policy.reference_storage_key,
        )
        if not reference_images:
            return LetterImageResult(status="failed", failure_code="reference_unavailable")
        prompt = _build_prompt(image_brief)
        last_error = "image_generation_failed"
        for attempt in range(1, self.policy.maximum_attempts + 1):
            remaining = _remaining_seconds(deadline, self.clock())
            if remaining is not None and remaining <= 0:
                return LetterImageResult(
                    status="failed",
                    failure_code="publish_deadline_exceeded",
                )
            try:
                timeout = float(self.policy.timeout_seconds)
                if remaining is not None:
                    timeout = min(timeout, remaining)
                content, content_type = await asyncio.wait_for(
                    self.provider.generate(
                        prompt=prompt,
                        reference_images=reference_images,
                        aspect_ratio=self.policy.aspect_ratio,
                    ),
                    timeout=max(timeout, 0.001),
                )
                validate_image(content, content_type, self.policy.maximum_bytes)
                width, height = _image_dimensions(content, content_type)
                if width <= 0 or height <= 0:
                    raise ValueError("generated image dimensions are invalid")
                if deadline is not None and self.clock() >= deadline:
                    return LetterImageResult(
                        status="failed",
                        failure_code="publish_deadline_exceeded",
                    )
                extension = {
                    "image/jpeg": "jpg",
                    "image/webp": "webp",
                    "image/gif": "gif",
                }.get(content_type, "png")
                user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
                relative_key = f"letters/{user_hash}/{local_date}/{letter_id}.{extension}"
                storage_key = self.storage.put_bytes(
                    relative_key,
                    content,
                    content_type,
                    cache_control="private, max-age=300",
                )
                return LetterImageResult(
                    storage_key=storage_key,
                    content_type=content_type,
                    byte_size=len(content),
                    provider=self.policy.provider_name,
                    model=self.policy.model,
                    reference_version=self.policy.reference_version,
                    width=width,
                    height=height,
                    status="succeeded",
                )
            except Exception as exc:
                last_error = type(exc).__name__
                logger.warning(
                    "Daily letter image generation failed letter_id=%s attempt=%s/%s",
                    letter_id,
                    attempt,
                    self.policy.maximum_attempts,
                    exc_info=True,
                )
        return LetterImageResult(status="failed", failure_code=last_error)


def _build_prompt(image_brief: dict[str, object]) -> str:
    emotion = str(image_brief.get("emotion") or "quiet and warm")[:300]
    scene = str(image_brief.get("scene") or "a calm Echo moment")[:800]
    symbols = image_brief.get("visual_symbols") or []
    avoid = image_brief.get("avoid") or []
    symbol_text = (
        ", ".join(str(value)[:100] for value in symbols)
        if isinstance(symbols, list)
        else ""
    )
    avoid_text = (
        ", ".join(str(value)[:100] for value in avoid)
        if isinstance(avoid, list)
        else ""
    )
    return (
        "Create one polished Echo character illustration for a private daily letter. "
        "Keep the official Echo character identity, outfit language, proportions and "
        "gentle visual style. Do not draw any readable text, logo, watermark, chat UI, "
        "user portrait or extra main character. "
        f"Emotion: {emotion}. Scene: {scene}. Visual symbols: {symbol_text}. Avoid: {avoid_text}."
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _signed_reference_url(storage: LetterImageStorage, storage_key: str) -> tuple[str, ...]:
    if not storage_key:
        return ()
    return (storage.download_url(storage_key),)


def _remaining_seconds(deadline: datetime | None, now: datetime) -> float | None:
    if deadline is None:
        return None
    return (deadline.astimezone(UTC) - now.astimezone(UTC)).total_seconds()


def _image_dimensions(content: bytes, content_type: str) -> tuple[int, int]:
    if content_type == "image/png" and len(content) >= 24:
        return struct.unpack(">II", content[16:24])
    if content_type == "image/gif" and len(content) >= 10:
        return struct.unpack("<HH", content[6:10])
    if content_type == "image/webp":
        return _webp_dimensions(content)
    if content_type == "image/jpeg":
        return _jpeg_dimensions(content)
    raise ValueError("unsupported generated image type")


def _webp_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ValueError("invalid WebP image")
    chunk = content[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(content[24:27], "little")
        height = 1 + int.from_bytes(content[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(content) >= 30:
        width = int.from_bytes(content[26:28], "little") & 0x3FFF
        height = int.from_bytes(content[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(content) >= 25:
        bits = int.from_bytes(content[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ValueError("unsupported WebP image")


def _jpeg_dimensions(content: bytes) -> tuple[int, int]:
    index = 2
    while index + 9 < len(content):
        if content[index] != 0xFF:
            index += 1
            continue
        marker = content[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(content):
            break
        segment_length = int.from_bytes(content[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(content):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(content[index + 3 : index + 5], "big")
            width = int.from_bytes(content[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    raise ValueError("invalid JPEG image")
