from __future__ import annotations

import base64
from typing import Protocol

import httpx

from shared.config import settings


class ImageGenerationProvider(Protocol):
    async def generate(self, prompt: str) -> tuple[bytes, str]: ...


class OpenAICompatibleImageGenerationProvider:
    async def generate(self, prompt: str) -> tuple[bytes, str]:
        if not settings.image_generation_base_url or not settings.image_generation_api_key:
            raise RuntimeError("Image generation provider is not configured")
        headers = {
            "Authorization": f"Bearer {settings.image_generation_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "size": "1024x1024",
            "response_format": "b64_json",
            "n": 1,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                settings.image_generation_base_url, headers=headers, json=payload
            )
            response.raise_for_status()
            encoded = response.json()["data"][0]["b64_json"]
        return base64.b64decode(encoded, validate=True), "image/png"

