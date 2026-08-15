from __future__ import annotations

import logging
from typing import Protocol, cast

import httpx
from shared.config import settings

from providers.registry import get_provider

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    async def create_embedding(self, text: str, model: str | None = None) -> list[float]:
        ...


class OpenAICompatibleEmbeddingProvider:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.timeout,
                limits=httpx.Limits(keepalive_expiry=300),
            )
        return self._client

    async def create_embedding(self, text: str, model: str | None = None) -> list[float]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Embedding input cannot be empty")
        if not settings.embedding_api_key:
            raise ValueError("Embedding service is not configured")

        url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.embedding_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or settings.embedding_model,
            "input": clean_text,
        }

        try:
            response = await self._http_client().post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTPStatusError from embedding API status=%s response_length=%s",
                exc.response.status_code,
                len(exc.response.text or ""),
            )
            raise ValueError(
                f"Embedding service responded with status {exc.response.status_code}"
            ) from exc
        except Exception as exc:
            logger.error("Error requesting embedding: %s", exc)
            raise ValueError("Failed to request embedding service") from exc

        if not isinstance(embedding, list):
            raise ValueError("Embedding response format is invalid")
        return [float(value) for value in embedding]


def get_embedding_provider() -> EmbeddingProvider:
    return cast(EmbeddingProvider, get_provider("embedding", OpenAICompatibleEmbeddingProvider))
