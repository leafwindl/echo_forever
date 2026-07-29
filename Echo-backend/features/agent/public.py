from features.agent.domain.entities import AgentEnrichment
from features.agent.infrastructure.container import get_chat_agent
from shared.config import settings


async def enrich_chat(user_id: str, message: str) -> AgentEnrichment:
    if not settings.agent_enabled:
        return AgentEnrichment()
    return await get_chat_agent().execute(user_id, message)


__all__ = ["AgentEnrichment", "enrich_chat"]
