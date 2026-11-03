from __future__ import annotations

from functools import lru_cache

from shared.config import settings

from features.presence.application.presence_service import PresenceService
from features.presence.infrastructure.adapters import (
    ChatPresenceContextSource,
    ChatPresenceMessageDelivery,
    DesktopPresenceActionExecutor,
    MemoryPresenceSource,
    MemoryPresenceWriter,
    ProactiveQuietHours,
)
from features.presence.infrastructure.message_composer import (
    ProviderPresenceMessageComposer,
)
from features.presence.infrastructure.postgres_repository import (
    PostgresPresenceRepository,
)
from features.presence.infrastructure.thought_generator import (
    ProviderPresenceThoughtGenerator,
)


@lru_cache(maxsize=1)
def get_presence_service() -> PresenceService:
    return PresenceService(
        repository=PostgresPresenceRepository(),
        context_source=ChatPresenceContextSource(),
        memory_source=MemoryPresenceSource(),
        thought_generator=ProviderPresenceThoughtGenerator(
            max_tokens=settings.presence_thought_max_tokens,
            temperature=settings.presence_thought_temperature,
        ),
        message_composer=ProviderPresenceMessageComposer(
            max_tokens=settings.presence_message_max_tokens,
            temperature=settings.presence_message_temperature,
        ),
        message_delivery=ChatPresenceMessageDelivery(),
        memory_writer=MemoryPresenceWriter(),
        action_executor=DesktopPresenceActionExecutor(),
        quiet_hours=ProactiveQuietHours(),
        active_window_minutes=settings.presence_active_window_minutes,
        silence_minutes=settings.presence_silence_minutes,
        min_thought_interval_minutes=settings.presence_min_thought_interval_minutes,
        daily_thought_budget=settings.presence_daily_thought_budget,
        proactive_message_budget=settings.presence_proactive_message_budget,
        proactive_message_interval_minutes=(
            settings.presence_proactive_message_interval_minutes
        ),
        proactive_action_budget=settings.presence_proactive_action_budget,
        proactive_action_interval_minutes=(
            settings.presence_proactive_action_interval_minutes
        ),
        message_min_salience=settings.presence_message_min_salience,
        memory_salience_threshold=settings.presence_memory_salience_threshold,
        context_messages=settings.presence_context_messages,
        max_candidate_users=settings.presence_max_candidate_users,
    )


def reset_presence_service_for_tests() -> None:
    get_presence_service.cache_clear()
