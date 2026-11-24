from __future__ import annotations

from functools import lru_cache

from shared.config import settings

from features.presence.application.presence_service import PresenceService
from features.presence.infrastructure.adapters import (
    ChatPresenceContextSource,
    MemoryPresenceSource,
    MemoryPresenceWriter,
    ProactivePresenceGoalCreator,
    ProactiveQuietHours,
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
        goal_creator=ProactivePresenceGoalCreator(),
        memory_writer=MemoryPresenceWriter(),
        quiet_hours=ProactiveQuietHours(),
        interaction_window_minutes=settings.presence_interaction_window_minutes,
        daily_thought_budget=settings.presence_daily_thought_budget,
        message_min_salience=settings.presence_message_min_salience,
        memory_salience_threshold=settings.presence_memory_salience_threshold,
        context_messages=settings.presence_context_messages,
        max_candidate_users=settings.presence_max_candidate_users,
        active_interval_minutes=settings.presence_active_interval_minutes,
        idle_interval_minutes=settings.presence_idle_interval_minutes,
        sleeping_interval_minutes=settings.presence_sleeping_interval_minutes,
        downshift_interval_minutes=settings.presence_downshift_interval_minutes,
        daily_activity_minimum=settings.presence_daily_activity_minimum,
        activity_interval_minutes=settings.presence_activity_interval_minutes,
        skip_threshold=settings.presence_skip_threshold,
        l2_daily_limit=settings.presence_l2_daily_limit,
    )


def reset_presence_service_for_tests() -> None:
    get_presence_service.cache_clear()
