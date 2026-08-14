import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import httpx
from shared.config import settings

from providers.registry import get_provider

logger = logging.getLogger(__name__)


class LLMProviderTimeoutError(TimeoutError):
    """The upstream LLM provider did not answer before its request timeout."""


@dataclass(frozen=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderAssistantMessage:
    content: str = ""
    tool_calls: tuple[ProviderToolCall, ...] = field(default_factory=tuple)
    finish_reason: str = ""
    request_id: str = ""


class LLMProvider(Protocol):
    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...

    async def chat_completion_message(
        self,
        messages: list[dict],
        tools: tuple[dict, ...] | list[dict] = (),
        tool_choice: str | dict[str, Any] = "auto",
        response_format: dict[str, str] | None = None,
        thinking: dict[str, str] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderAssistantMessage: ...


class OpenAICompatibleLLMProvider:
    @staticmethod
    def _request_options(
        messages: list[dict],
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
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
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        response = await self.chat_completion_message(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content

    async def chat_completion_message(
        self,
        messages: list[dict],
        tools: tuple[dict, ...] | list[dict] = (),
        tool_choice: str | dict[str, Any] = "auto",
        response_format: dict[str, str] | None = None,
        thinking: dict[str, str] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderAssistantMessage:
        url, headers, payload = self._request_options(
            messages,
            model,
            temperature,
            max_tokens,
        )
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = response_format
        if thinking is not None:
            payload["thinking"] = thinking

        try:
            async with httpx.AsyncClient(timeout=settings.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice.get("message") or {}
                parsed_calls = []
                for raw_call in message.get("tool_calls") or []:
                    function = raw_call.get("function") or {}
                    raw_arguments = function.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw_arguments)
                    except (TypeError, json.JSONDecodeError):
                        arguments = {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    parsed_calls.append(
                        ProviderToolCall(
                            call_id=str(raw_call.get("id") or ""),
                            name=str(function.get("name") or ""),
                            arguments=arguments,
                        )
                    )
                return ProviderAssistantMessage(
                    content=str(message.get("content") or ""),
                    tool_calls=tuple(parsed_calls),
                    finish_reason=str(choice.get("finish_reason") or ""),
                    request_id=str(data.get("id") or response.headers.get("x-request-id") or ""),
                )
        except httpx.TimeoutException as exc:
            logger.warning("LLM request timed out timeout_seconds=%s", settings.timeout)
            raise LLMProviderTimeoutError("LLM provider request timed out") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTPStatusError from LLM status=%s response_length=%s",
                exc.response.status_code,
                len(exc.response.text or ""),
            )
            raise ValueError(
                f"LLM service responded with status {exc.response.status_code}"
            ) from exc
        except Exception as exc:
            logger.error("Error requesting LLM: %s", exc)
            raise ValueError("Failed to request LLM service") from exc


def get_llm_provider() -> LLMProvider:
    return cast(LLMProvider, get_provider("llm", OpenAICompatibleLLMProvider))
