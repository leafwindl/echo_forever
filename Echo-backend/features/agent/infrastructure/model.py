from collections.abc import Awaitable, Callable
from typing import Any

from providers.llm_provider import LLMProviderTimeoutError, get_llm_provider

from features.agent.domain.entities import AgentModelResponse, AgentToolCall
from features.agent.domain.services import AgentModelTimeoutError


class ProviderAgentConversationModel:
    def __init__(
        self,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        disable_thinking: bool = False,
    ):
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.disable_thinking = disable_thinking

    async def complete(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        *,
        structured_output: bool = False,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AgentModelResponse:
        try:
            response = await get_llm_provider().chat_completion_message(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                response_format={"type": "json_object"} if structured_output else None,
                thinking=(
                    {"type": "disabled"}
                    if structured_output or self.disable_thinking
                    else None
                ),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except LLMProviderTimeoutError as exc:
            raise AgentModelTimeoutError("Conversation model request timed out") from exc
        return AgentModelResponse(
            text=response.content,
            tool_calls=tuple(
                AgentToolCall(
                    call_id=call.call_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                )
                for call in response.tool_calls
            ),
            finish_reason=response.finish_reason,
            provider_request_id=response.request_id,
        )

    async def stream_complete(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        *,
        structured_output: bool = False,
        tool_choice: str | dict[str, Any] = "auto",
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentModelResponse:
        try:
            provider = get_llm_provider()
            stream_method = getattr(provider, "stream_chat_completion_message", None)
            if stream_method is None:
                response = await provider.chat_completion_message(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format={"type": "json_object"} if structured_output else None,
                    thinking=(
                        {"type": "disabled"}
                        if structured_output or self.disable_thinking
                        else None
                    ),
                    max_tokens=self.max_tokens,
                )
                if on_text_delta is not None and response.content:
                    await on_text_delta(response.content)
            else:
                response = await stream_method(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format={"type": "json_object"} if structured_output else None,
                    thinking=(
                        {"type": "disabled"}
                        if structured_output or self.disable_thinking
                        else None
                    ),
                    max_tokens=self.max_tokens,
                    on_text_delta=on_text_delta,
                )
        except LLMProviderTimeoutError as exc:
            raise AgentModelTimeoutError("Conversation model streaming request timed out") from exc
        return AgentModelResponse(
            text=response.content,
            tool_calls=tuple(
                AgentToolCall(
                    call_id=call.call_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                )
                for call in response.tool_calls
            ),
            finish_reason=response.finish_reason,
            provider_request_id=response.request_id,
        )
