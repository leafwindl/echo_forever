import logging
from typing import Optional, Protocol, cast

import httpx

from providers.registry import get_provider
from shared.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        ...


class OpenAICompatibleLLMProvider:
    @staticmethod
    def _request_options(
        messages: list[dict],
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> tuple[str, dict[str, str], dict]:
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or settings.llm_model or "gpt-4o",
            "messages": messages,
            "temperature": settings.temperature if temperature is None else temperature,
            "max_tokens": settings.max_tokens if max_tokens is None else max_tokens,
        }
        return url, headers, payload

    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        url, headers, payload = self._request_options(
            messages,
            model,
            temperature,
            max_tokens,
        )

        try:
            async with httpx.AsyncClient(timeout=settings.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTPStatusError from LLM status=%s response_length=%s",
                exc.response.status_code,
                len(exc.response.text or ""),
            )
            raise ValueError(f"LLM service responded with status {exc.response.status_code}") from exc
        except Exception as exc:
            logger.error("Error requesting LLM: %s", exc)
            raise ValueError("Failed to request LLM service") from exc


def get_llm_provider() -> LLMProvider:
    return cast(LLMProvider, get_provider("llm", OpenAICompatibleLLMProvider))
