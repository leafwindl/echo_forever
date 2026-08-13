from functools import lru_cache

from providers.web_search_provider import TavilyWebSearchProvider
from shared.config import settings

from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.services import SystemClock
from features.agent.domain.tools import ToolRegistry
from features.agent.infrastructure.model import ProviderAgentConversationModel
from features.agent.infrastructure.postgres_repository import PostgresAgentRunRepository
from features.agent.infrastructure.tools import (
    register_schedule_tools,
    register_sticker_tools,
    register_time_tool,
    register_web_search_tool,
)


@lru_cache(maxsize=1)
def get_chat_agent() -> OrchestrateChatWithAgent:
    registry = ToolRegistry()
    register_sticker_tools(registry)
    register_schedule_tools(registry)
    register_time_tool(registry, SystemClock(), settings.default_user_timezone)
    register_web_search_tool(registry, TavilyWebSearchProvider())
    return OrchestrateChatWithAgent(
        repository=PostgresAgentRunRepository(),
        model=ProviderAgentConversationModel(
            max_tokens=settings.chat_max_tokens,
            disable_thinking=True,
        ),
        registry=registry,
        executor=ToolExecutor(registry),
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        run_timeout_seconds=settings.agent_run_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_daily_letter_agent() -> OrchestrateChatWithAgent:
    registry = ToolRegistry()
    return OrchestrateChatWithAgent(
        repository=PostgresAgentRunRepository(),
        model=ProviderAgentConversationModel(max_tokens=settings.daily_letter_max_tokens),
        registry=registry,
        executor=ToolExecutor(registry),
        max_steps=settings.daily_letter_agent_max_steps,
        max_tool_calls=1,
        run_timeout_seconds=settings.daily_letter_agent_timeout_seconds,
    )
