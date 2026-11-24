from __future__ import annotations

from features.proactive_chat.application.worker import ProcessProactiveChatJobs
from features.proactive_chat.domain.entities import ProactiveChatPreferences
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)

_worker: ProcessProactiveChatJobs | None = None


def get_proactive_repository() -> PostgresProactiveChatRepository:
    return PostgresProactiveChatRepository()


def get_proactive_preferences(user_id: str) -> ProactiveChatPreferences:
    return get_proactive_repository().get_preferences(user_id)


def get_proactive_worker() -> ProcessProactiveChatJobs:
    global _worker
    if _worker is None:
        from shared.config import settings

        from features.chat.infrastructure.adapters import InMemoryChatRequestGuard
        from features.chat.infrastructure.container import (
            get_delivery_timing_policy,
            get_generate_chat_reply_use_case,
        )
        from features.chat.infrastructure.events import get_chat_event_broker

        _worker = ProcessProactiveChatJobs(
            repository=get_proactive_repository(),
            reply_generator=get_generate_chat_reply_use_case(),
            request_guard=InMemoryChatRequestGuard(),
            event_broker=get_chat_event_broker(),
            timing_policy=get_delivery_timing_policy(),
            lease_seconds=settings.proactive_chat_job_lease_seconds,
            daily_budget=settings.proactive_daily_budget,
            allow_spontaneous_jobs=not settings.presence_enabled,
        )
    return _worker


async def process_proactive_chat_once() -> bool:
    return await get_proactive_worker().run_once()


def create_proactive_goal(
    *,
    user_id: str,
    intent: str,
    draft_text: str,
    trigger_type: str = "presence",
    trigger_ref: str = "",
    action_intent: str = "",
    plan: str = "",
) -> str:
    """写入一次主动意图并排队投递；命中 48 小时去重时返回空字符串。"""
    goal = get_proactive_repository().create_goal(
        user_id=user_id,
        trigger_type=trigger_type,
        intent=intent,
        draft_text=draft_text,
        trigger_ref=trigger_ref,
        action_intent=action_intent,
        plan=plan,
    )
    return goal.goal_id if goal is not None else ""


def pending_goal_summaries(user_id: str, limit: int = 3) -> list[str]:
    """还没做完的主动目标，供 presence briefing 参考。"""
    rows = get_proactive_repository().pending_goals(user_id, limit)
    summaries: list[str] = []
    for row in rows:
        text = str(row.get("plan") or row.get("intent") or "").strip()
        if text:
            summaries.append(text[:160])
    return summaries


def recent_goal_summaries(user_id: str, limit: int = 3) -> list[dict]:
    """最近完成的主动动作摘要，供 presence 念头参考。"""
    rows = get_proactive_repository().recent_reported_goals(user_id, limit)
    return [
        {
            "kind": "goal",
            "summary": str(row.get("result_summary") or row.get("intent") or "")[:200],
            "occurred_at": row.get("reported_at"),
        }
        for row in rows
    ]


def reset_user_proactive_state(user_id: str) -> None:
    """Reset preferences, reminders and queued jobs for a new companionship cycle."""
    get_proactive_repository().reset_user_state(user_id)


__all__ = [
    "create_proactive_goal",
    "get_proactive_preferences",
    "get_proactive_repository",
    "process_proactive_chat_once",
    "pending_goal_summaries",
    "recent_goal_summaries",
    "reset_user_proactive_state",
]
