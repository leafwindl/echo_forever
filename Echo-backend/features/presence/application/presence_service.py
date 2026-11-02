from __future__ import annotations

import difflib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from features.presence.domain.entities import (
    PresenceState,
    PresenceStatus,
    PresenceThought,
    PresenceTickResult,
)
from features.presence.domain.ports import (
    PresenceContextSource,
    PresenceMemorySource,
    PresenceMessageComposer,
    PresenceMessageDelivery,
    PresenceQuietHours,
    PresenceRepository,
    PresenceThoughtGenerator,
)

logger = logging.getLogger(__name__)


def _compact(value: str, limit: int = 500) -> str:
    return " ".join(value.split())[:limit]


def _is_duplicate(text: str, recent: tuple[PresenceThought, ...]) -> bool:
    candidate = _compact(text, 220)
    for thought in recent:
        previous = _compact(thought.text, 220)
        if not previous:
            continue
        if difflib.SequenceMatcher(None, candidate, previous).ratio() >= 0.86:
            return True
    return False


class PresenceService:
    def __init__(
        self,
        *,
        repository: PresenceRepository,
        context_source: PresenceContextSource,
        memory_source: PresenceMemorySource,
        thought_generator: PresenceThoughtGenerator,
        message_composer: PresenceMessageComposer,
        message_delivery: PresenceMessageDelivery,
        quiet_hours: PresenceQuietHours,
        active_window_minutes: int,
        silence_minutes: int,
        min_thought_interval_minutes: int,
        daily_thought_budget: int,
        proactive_message_budget: int,
        proactive_message_interval_minutes: int,
        context_messages: int,
        max_candidate_users: int,
    ):
        self.repository = repository
        self.context_source = context_source
        self.memory_source = memory_source
        self.thought_generator = thought_generator
        self.message_composer = message_composer
        self.message_delivery = message_delivery
        self.quiet_hours = quiet_hours
        self.active_window = timedelta(minutes=active_window_minutes)
        self.silence_window = timedelta(minutes=silence_minutes)
        self.thought_interval = timedelta(minutes=min_thought_interval_minutes)
        self.daily_thought_budget = daily_thought_budget
        self.proactive_message_budget = proactive_message_budget
        self.proactive_message_interval = timedelta(
            minutes=proactive_message_interval_minutes
        )
        self.context_messages = context_messages
        self.max_candidate_users = max_candidate_users

    def state(self, user_id: str) -> PresenceState:
        return self.repository.get_or_create_state(user_id)

    def thoughts(self, user_id: str, limit: int = 20) -> list[PresenceThought]:
        return self.repository.recent_thoughts(user_id, limit)

    async def tick(self, user_id: str, *, now: datetime | None = None) -> PresenceTickResult:
        current = now or datetime.now(UTC)
        state = self.repository.get_or_create_state(user_id)
        context = await self.context_source.load(user_id, self.context_messages)
        last_user_at = context.last_user_message_at
        status = (
            PresenceStatus.ACTIVE
            if last_user_at is not None and current - last_user_at <= self.active_window
            else PresenceStatus.IDLE
        )
        if self.quiet_hours.is_quiet(user_id, current):
            status = PresenceStatus.SLEEPING

        state = self._with_activity(state, status, last_user_at, current)
        if not state.enabled:
            return self._finish(state, "skipped", "presence_disabled", current)

        budget_date = current.date()
        if state.thought_budget_date != budget_date:
            state = PresenceState(
                **{
                    **state.__dict__,
                    "thought_budget_date": budget_date,
                    "thoughts_used": 0,
                }
            )
        if status == PresenceStatus.ACTIVE:
            return self._finish(state, "skipped", "user_active", current)
        if status == PresenceStatus.SLEEPING:
            return self._finish(state, "skipped", "quiet_hours", current)
        if last_user_at is None:
            return self._finish(state, "skipped", "no_activity", current)
        silence = current - last_user_at
        if silence < self.silence_window:
            return self._finish(state, "skipped", "too_recent", current)
        if state.thoughts_used >= self.daily_thought_budget:
            return self._finish(state, "skipped", "daily_budget", current)
        if (
            state.last_thought_at is not None
            and current - state.last_thought_at < self.thought_interval
        ):
            return self._finish(state, "skipped", "thought_cooldown", current)

        recent = tuple(self.repository.recent_thoughts(user_id, 3))
        query = _compact(context.last_user_text or context.recent_assistant_text, 300)
        if not query:
            return self._finish(state, "skipped", "no_context", current)

        try:
            memory = await self.memory_source.recall(user_id, query)
            draft = await self.thought_generator.generate(
                state=state,
                context=context,
                memory=memory,
                recent_thoughts=recent,
                now=current,
            )
        except Exception as exc:
            self.repository.record_event(
                user_id=user_id,
                event_type="thought_failed",
                detail={"error": type(exc).__name__},
                now=current,
            )
            logger.warning("Presence thought generation failed user_id=%s", user_id, exc_info=True)
            return self._finish(state, "failed", "generation_failed", current)

        cleaned = _compact(draft.text)
        if not cleaned:
            return self._finish(state, "skipped", "empty_thought", current)
        if _is_duplicate(cleaned, recent):
            return self._finish(state, "skipped", "duplicate_thought", current)

        thought = PresenceThought(
            thought_id=f"thought_{uuid.uuid4().hex}",
            user_id=user_id,
            text=cleaned,
            salience=max(0.0, min(float(draft.salience), 1.0)),
            shareable=bool(draft.shareable),
            action_intent=_compact(draft.action_intent, 160),
            source_memory_id=memory.memory_id if memory else "",
            source_memory_text=_compact(memory.content, 500) if memory else "",
            created_at=current,
        )
        self.repository.add_thought(thought)
        state = PresenceState(
            **{
                **state.__dict__,
                "last_thought_at": current,
                "thoughts_used": state.thoughts_used + 1,
                "last_decision": "thought",
                "last_decision_reason": "inner_thought",
                "last_tick_at": current,
            }
        )
        self.repository.save_state(state)
        self.repository.record_event(
            user_id=user_id,
            event_type="thought_created",
            detail={"thought_id": thought.thought_id, "salience": thought.salience},
            now=current,
        )
        message_text = ""
        if thought.shareable:
            message_text = await self._maybe_deliver_message(
                state=state,
                thought=thought,
                context=context,
                now=current,
            )
            if message_text:
                state = PresenceState(
                    **{
                        **state.__dict__,
                        "last_proactive_message_at": current,
                        "proactive_messages_used": (
                            0
                            if state.proactive_budget_date != current.date()
                            else state.proactive_messages_used
                        )
                        + 1,
                        "proactive_budget_date": current.date(),
                        "last_decision": "message",
                        "last_decision_reason": "proactive_message",
                        "last_tick_at": current,
                    }
                )
                self.repository.save_state(state)
        return PresenceTickResult(
            user_id=user_id,
            status=state.status,
            decision="message" if message_text else "thought",
            reason="proactive_message" if message_text else "inner_thought",
            thought=thought,
            message_text=message_text,
            thoughts_used=state.thoughts_used,
        )

    async def _maybe_deliver_message(
        self,
        *,
        state: PresenceState,
        thought: PresenceThought,
        context,
        now: datetime,
    ) -> str:
        used = (
            state.proactive_messages_used
            if state.proactive_budget_date == now.date()
            else 0
        )
        if used >= self.proactive_message_budget:
            return ""
        if not self.quiet_hours.can_send_spontaneous(state.user_id, now):
            return ""
        if (
            state.last_proactive_message_at is not None
            and now - state.last_proactive_message_at < self.proactive_message_interval
        ):
            return ""
        if (
            context.last_assistant_at is not None
            and now - context.last_assistant_at < self.proactive_message_interval
        ):
            return ""
        try:
            text = await self.message_composer.compose(
                thought=thought,
                context=context,
                now=now,
            )
        except Exception:
            logger.warning(
                "Presence message compose failed user_id=%s",
                state.user_id,
                exc_info=True,
            )
            self.repository.record_event(
                user_id=state.user_id,
                event_type="message_compose_failed",
                detail={"thought_id": thought.thought_id},
                now=now,
            )
            return ""
        if not text.strip():
            return ""
        try:
            awaited = self.message_delivery.deliver(
                user_id=state.user_id,
                thought_id=thought.thought_id,
                text=text,
            )
            await awaited
        except Exception:
            logger.warning(
                "Presence message delivery failed user_id=%s",
                state.user_id,
                exc_info=True,
            )
            self.repository.record_event(
                user_id=state.user_id,
                event_type="message_delivery_failed",
                detail={"thought_id": thought.thought_id},
                now=now,
            )
            return ""
        self.repository.record_event(
            user_id=state.user_id,
            event_type="message_delivered",
            detail={"thought_id": thought.thought_id, "text": text[:160]},
            now=now,
        )
        return text

    async def run_once(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        processed = 0
        for user_id in self.context_source.recent_user_ids(self.max_candidate_users):
            result = await self.tick(user_id, now=current)
            if result.decision == "thought":
                processed += 1
            if result.status == PresenceStatus.ACTIVE:
                continue
        return processed

    def _with_activity(self, state, status, last_user_at, now) -> PresenceState:
        return PresenceState(
            **{
                **state.__dict__,
                "status": status,
                "last_user_message_at": last_user_at,
                "last_tick_at": now,
            }
        )

    def _finish(self, state, decision: str, reason: str, now) -> PresenceTickResult:
        state = PresenceState(
            **{
                **state.__dict__,
                "last_decision": decision,
                "last_decision_reason": reason,
                "last_tick_at": now,
            }
        )
        self.repository.save_state(state)
        return PresenceTickResult(
            user_id=state.user_id,
            status=state.status,
            decision=decision,
            reason=reason,
            thoughts_used=state.thoughts_used,
        )
