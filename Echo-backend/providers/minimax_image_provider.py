from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class MiniMaxImageProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: int


class MiniMaxImageGenerationProvider:
    """MiniMax image adapter; request details stay outside the letter feature."""

    def __init__(self, config: MiniMaxImageProviderConfig):
        self.config = config

    async def generate(
        self,
        *,
        prompt: str,
        reference_images: tuple[str, ...] = (),
        aspect_ratio: str = "4:3",
    ) -> tuple[bytes, str]:
        if not self.config.api_key.strip():
            raise RuntimeError("MiniMax image provider is not configured")
        if not self.config.base_url.strip():
            raise RuntimeError("MINIMAX_IMAGE_BASE_URL is not configured")
        payload = self._request_payload(prompt, reference_images, aspect_ratio)
        headers = {
            "Authorization": f"Bearer {self.config.api_key.strip()}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            trust_env=False,
        ) as client:
            response = await client.post(
                self.config.base_url.strip(),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return await self._parse_response(response, client)

    def _request_payload(
        self,
        prompt: str,
        reference_images: tuple[str, ...],
        aspect_ratio: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model.strip(),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": 1,
            "response_format": "url",
            "prompt_optimizer": False,
            "aigc_watermark": False,
        }
        if reference_images:
            payload["subject_reference"] = [
                {"type": "character", "image_file": image_url}
                for image_url in reference_images
            ]
        return payload

    @staticmethod
    async def _parse_response(
        response: httpx.Response,
        client: httpx.AsyncClient,
    ) -> tuple[bytes, str]:
        payload = response.json()
        candidates: list[Any] = []
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                candidates.extend(data)
            elif isinstance(data, dict):
                for key in ("image_urls", "images", "urls"):
                    value = data.get(key)
                    if isinstance(value, list):
                        candidates.extend(value)
                for key in ("image", "image_url", "url", "b64_json", "base64"):
                    if key in data:
                        candidates.append(data[key])
            elif data is not None:
                candidates.append(data)
            images = payload.get("images")
            if isinstance(images, list):
                candidates.extend(images)
            for key in ("image", "image_url", "url", "b64_json", "base64"):
                if key in payload:
                    candidates.append(payload[key])
        for candidate in candidates:
            image = await MiniMaxImageGenerationProvider._decode_candidate(candidate, client)
            if image is not None:
                return image
        raise ValueError("MiniMax image response did not contain an image")

    @staticmethod
    async def _decode_candidate(
        candidate: Any,
        client: httpx.AsyncClient,
    ) -> tuple[bytes, str] | None:
        if isinstance(candidate, dict):
            for key in ("b64_json", "base64", "image_base64", "data"):
                if candidate.get(key):
                    return _decode_base64(str(candidate[key]), candidate.get("mime_type"))
            for key in ("url", "image_url"):
                if candidate.get(key):
                    return await _download_image(client, str(candidate[key]))
            return None
        if not isinstance(candidate, str) or not candidate.strip():
            return None
        value = candidate.strip()
        if value.startswith("data:") and ";base64," in value:
            header, encoded = value.split(",", 1)
            return _decode_base64(encoded, header[5:].split(";", 1)[0])
        if value.startswith("http://") or value.startswith("https://"):
            return await _download_image(client, value)
        return _decode_base64(value, None)


def _decode_base64(encoded: str, content_type: Any) -> tuple[bytes, str]:
    content = base64.b64decode(encoded, validate=True)
    return content, str(content_type or "image/png")


async def _download_image(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[bytes, str]:
    response = await client.get(url)
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "image/png").split(";", 1)[0]
