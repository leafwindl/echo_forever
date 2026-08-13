from providers.llm_provider import LLMProviderTimeoutError, get_llm_provider

from features.agent.domain.entities import AgentModelResponse, AgentToolCall
from features.agent.domain.services import AgentModelTimeoutError


class ProviderAgentConversationModel:
    def __init__(
        self,
        *,
        max_tokens: int | None = None,
        disable_thinking: bool = False,
    ):
        self.max_tokens = max_tokens
        self.disable_thinking = disable_thinking

    async def complete(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        *,
        structured_output: bool = False,
    ) -> AgentModelResponse:
        try:
            response = await get_llm_provider().chat_completion_message(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                response_format={"type": "json_object"} if structured_output else None,
                thinking=(
                    {"type": "disabled"}
                    if structured_output or self.disable_thinking
                    else None
                ),
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
