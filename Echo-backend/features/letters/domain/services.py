from __future__ import annotations

from typing import Protocol


class LetterImageGenerator(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        reference_images: tuple[str, ...] = (),
        aspect_ratio: str = "4:3",
    ) -> tuple[bytes, str]: ...


class LetterImageStorage(Protocol):
    def put_bytes(
        self,
        relative_key: str,
        content: bytes,
        content_type: str,
        *,
        cache_control: str | None = None,
    ) -> str: ...

    def download_url(
        self,
        relative_key: str,
        expires_seconds: int | None = None,
        *,
        download_name: str | None = None,
    ) -> str: ...
