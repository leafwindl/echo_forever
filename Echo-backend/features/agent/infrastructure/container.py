from functools import lru_cache

from features.agent.application.enrich_chat import EnrichChatWithAgent
from features.agent.domain.services import SystemClock
from features.agent.infrastructure.postgres_repository import PostgresAgentRunRepository
from providers.web_search_provider import TavilyWebSearchProvider
from shared.config import settings


@lru_cache(maxsize=1)
def get_chat_agent() -> EnrichChatWithAgent:
    return EnrichChatWithAgent(
        repository=PostgresAgentRunRepository(),
        clock=SystemClock(),
        web_search=TavilyWebSearchProvider(),
        timezone_name=settings.default_user_timezone,
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
    )

