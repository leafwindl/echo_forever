import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def create_embedding(text: str, model: Optional[str] = None) -> list[float]:
    """调用 embedding API，把文本转换成向量。"""
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
        async with httpx.AsyncClient(timeout=settings.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
    except httpx.HTTPStatusError as exc:
        logger.error("HTTPStatusError from embedding API: %s", exc.response.text)
        raise ValueError(f"Embedding 服务响应错误: {exc.response.status_code}")
    except Exception as exc:
        logger.error("Error requesting embedding: %s", exc)
        raise ValueError("调用 Embedding 服务失败")

    if not isinstance(embedding, list):
        raise ValueError("Embedding response format is invalid")
    return [float(value) for value in embedding]
