from functools import lru_cache

from providers.web_search_provider import TavilyWebSearchProvider
from shared.config import settings

from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.tools import ToolRegistry
from features.agent.infrastructure.model import ProviderAgentConversationModel
from features.agent.infrastructure.postgres_repository import PostgresAgentRunRepository
from features.agent.infrastructure.proactive_planner import ProviderProactiveDecisionPlanner
from features.agent.infrastructure.tools import (
    register_beat_tools,
    register_desktop_tools,
    register_mobile_agent_tools,
    register_proactive_tools,
    register_relationship_tools,
    register_schedule_tools,
    register_sticker_tools,
    register_web_search_tool,
)


def _register_web_search_if_configured(registry: ToolRegistry) -> None:
    """未配置联网搜索时不要注册工具：宣布一个必然失败的能力比没有更糟。"""
    if not settings.web_search_enabled:
        return
    if not settings.web_search_api_key.strip():
        return
    register_web_search_tool(registry, TavilyWebSearchProvider())


@lru_cache(maxsize=1)
def get_chat_agent() -> OrchestrateChatWithAgent:
    registry = ToolRegistry()
    register_sticker_tools(registry)
    register_beat_tools(registry)
    register_desktop_tools(registry)
    register_mobile_agent_tools(registry)
    register_relationship_tools(registry)
    register_proactive_tools(registry)
    register_schedule_tools(registry)
    _register_web_search_if_configured(registry)
    chat_model = ProviderAgentConversationModel(
        max_tokens=settings.chat_max_tokens,
        disable_thinking=True,
    )
    return OrchestrateChatWithAgent(
        repository=PostgresAgentRunRepository(),
        model=chat_model,
        registry=registry,
        executor=ToolExecutor(registry),
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        run_timeout_seconds=settings.agent_run_timeout_seconds,
        proactive_max_tool_calls=settings.proactive_agent_max_tool_calls,
    )


@lru_cache(maxsize=1)
def get_call_agent() -> OrchestrateChatWithAgent:
    registry = ToolRegistry()
    register_schedule_tools(registry)
    _register_web_search_if_configured(registry)
    return OrchestrateChatWithAgent(
        repository=PostgresAgentRunRepository(),
        model=ProviderAgentConversationModel(
            max_tokens=settings.call_max_tokens,
            disable_thinking=True,
        ),
        registry=registry,
        executor=ToolExecutor(registry),
        max_steps=settings.agent_max_steps,
        max_tool_calls=2,
        run_timeout_seconds=settings.agent_run_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_proactive_planner() -> ProviderProactiveDecisionPlanner:
    return ProviderProactiveDecisionPlanner(
        ProviderAgentConversationModel(
            max_tokens=settings.proactive_planner_max_tokens,
            temperature=settings.proactive_planner_temperature,
            disable_thinking=True,
        ),
        format_retries=settings.proactive_planner_format_retries,
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
