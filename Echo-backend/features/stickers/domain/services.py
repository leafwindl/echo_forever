from __future__ import annotations

import hashlib
from typing import Protocol

ALLOWED_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}


class ImageGenerator(Protocol):
    """Domain-facing contract for asynchronous sticker image generation."""

    async def generate(self, prompt: str) -> tuple[bytes, str]: ...


def validate_image(content: bytes, content_type: str, maximum_bytes: int) -> str:
    if not content or len(content) > maximum_bytes:
        raise ValueError("表情包文件为空或超过大小限制")
    signatures = ALLOWED_SIGNATURES.get(content_type)
    if not signatures or not any(content.startswith(signature) for signature in signatures):
        raise ValueError("仅支持 PNG、JPEG、GIF 或 WebP 图片")
    if content_type == "image/webp" and content[8:12] != b"WEBP":
        raise ValueError("WebP 文件头无效")
    return hashlib.sha256(content).hexdigest()


def normalize_tags(tags: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tag.strip().lower()[:30] for tag in tags if tag.strip()))[:12]

