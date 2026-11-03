from __future__ import annotations

from functools import lru_cache

from shared.config import settings

from features.mobile_agent.application.hub import MobileAgentHub
from features.mobile_agent.application.management import MobileAgentManagement
from features.mobile_agent.application.service import MobileAgentService
from features.mobile_agent.infrastructure.postgres_repository import (
    PostgresMobileAgentRepository,
)


@lru_cache(maxsize=1)
def get_mobile_agent_hub() -> MobileAgentHub:
    return MobileAgentHub()


@lru_cache(maxsize=1)
def get_mobile_agent_repository() -> PostgresMobileAgentRepository:
    return PostgresMobileAgentRepository()


@lru_cache(maxsize=1)
def get_mobile_agent_management() -> MobileAgentManagement:
    return MobileAgentManagement(
        repository=get_mobile_agent_repository(),
        pairing_secret=settings.auth_token_secret,
        pairing_code_ttl_seconds=settings.mobile_agent_pairing_code_ttl_seconds,
    )


@lru_cache(maxsize=1)
def get_mobile_agent_service() -> MobileAgentService:
    return MobileAgentService(
        management=get_mobile_agent_management(),
        hub=get_mobile_agent_hub(),
        command_timeout_seconds=settings.mobile_agent_command_timeout_seconds,
    )


def reset_mobile_agent_services_for_tests() -> None:
    get_mobile_agent_service.cache_clear()
    get_mobile_agent_management.cache_clear()
    get_mobile_agent_repository.cache_clear()
    get_mobile_agent_hub.cache_clear()
