from __future__ import annotations

from functools import lru_cache

from shared.config import settings

from features.desktop.application.desktop_service import DesktopService
from features.desktop.application.manage_nodes import DesktopNodeManagement
from features.desktop.application.node_hub import DesktopNodeHub
from features.desktop.infrastructure.postgres_repository import PostgresDesktopRepository


@lru_cache(maxsize=1)
def get_desktop_node_hub() -> DesktopNodeHub:
    return DesktopNodeHub()


@lru_cache(maxsize=1)
def get_desktop_repository() -> PostgresDesktopRepository:
    return PostgresDesktopRepository()


@lru_cache(maxsize=1)
def get_desktop_node_management() -> DesktopNodeManagement:
    return DesktopNodeManagement(
        repository=get_desktop_repository(),
        pairing_secret=settings.auth_token_secret,
        pairing_code_ttl_seconds=settings.desktop_pairing_code_ttl_seconds,
    )


@lru_cache(maxsize=1)
def get_desktop_service() -> DesktopService:
    return DesktopService(
        repository=get_desktop_repository(),
        hub=get_desktop_node_hub(),
        management=get_desktop_node_management(),
        command_timeout_seconds=settings.desktop_command_timeout_seconds,
    )


def reset_desktop_services_for_tests() -> None:
    get_desktop_service.cache_clear()
    get_desktop_node_management.cache_clear()
    get_desktop_repository.cache_clear()
    get_desktop_node_hub.cache_clear()
