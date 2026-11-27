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
    PresenceGoalCreator,
    PresenceMemorySource,
    PresenceMemoryWriter,
    PresenceQuietHours,
    PresenceRepository,
    PresenceThoughtGenerator,
)

logger = logging.getLogger(__name__)

# 用户长时间没消息时，从这些低成本活动里挑一件做，避免一直空转。
_DEFAULT_AGENDA = (
    ("bili", "看看B站今天有什么", "bili"),
    ("bili", "看看有没有值得分享的视频", "bili"),
    ("selfie", "看看自己的屏幕", "selfie"),
    ("reflect", "整理一下最近的记忆", "reflect"),
    ("reflect", "准备一个可以聊的话题", "reflect"),
    ("look", "看看用户现在在忙什么", "look"),
    ("phone_look", "看看用户手机上有什么", "phone_look"),
    ("music", "找一首应景的歌", "music"),
    ("notepad", "写一张便签", "notepad"),
    ("sticker", "发个表情", "sticker"),
    ("propose", "问问用户要不要一起做点什么", "propose"),
)


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
        goal_creator: PresenceGoalCreator,
        memory_writer: PresenceMemoryWriter,
        quiet_hours: PresenceQuietHours,
        interaction_window_minutes: int = 20,
        daily_thought_budget: int = 12,
        message_min_salience: float = 0.3,
        memory_salience_threshold: float,
        context_messages: int,
        max_candidate_users: int,
        active_interval_minutes: int = 45,
        idle_interval_minutes: int = 60,
        sleeping_interval_minutes: int = 90,
        downshift_interval_minutes: int = 180,
        daily_activity_minimum: int = 5,
        activity_interval_minutes: int = 180,
        skip_threshold: int = 3,
        l2_daily_limit: int = 2,
        min_wake_minutes: int = 30,
        max_wake_minutes: int = 240,
    ):
        self.repository = repository
        self.context_source = context_source
        self.memory_source = memory_source
        self.thought_generator = thought_generator
        self.goal_creator = goal_creator
        self.memory_writer = memory_writer
        self.quiet_hours = quiet_hours
        self.interaction_window = timedelta(minutes=interaction_window_minutes)
        self.daily_thought_budget = daily_thought_budget
        self.message_min_salience = message_min_salience
        self.memory_salience_threshold = memory_salience_threshold
        self.context_messages = context_messages
        self.max_candidate_users = max_candidate_users
        self.active_interval = timedelta(minutes=active_interval_minutes)
        self.idle_interval = timedelta(minutes=idle_interval_minutes)
        self.sleeping_interval = timedelta(minutes=sleeping_interval_minutes)
        self.downshift_interval = timedelta(minutes=downshift_interval_minutes)
        self.daily_activity_minimum = daily_activity_minimum
        self.activity_interval = timedelta(minutes=activity_interval_minutes)
        self.skip_threshold = skip_threshold
        self.l2_daily_limit = l2_daily_limit
        self.min_wake_minutes = min_wake_minutes
        self.max_wake_minutes = max_wake_minutes

    def state(self, user_id: str) -> PresenceState:
        return self.repository.get_or_create_state(user_id)

    def thoughts(self, user_id: str, limit: int = 20) -> list[PresenceThought]:
        return self.repository.recent_thoughts(user_id, limit)

    async def tick(self, user_id: str, *, now: datetime | None = None) -> PresenceTickResult:
        current = now or datetime.now(UTC)
        state = self.repository.get_or_create_state(user_id)
        if state.next_tick_at is not None and current < state.next_tick_at:
            return PresenceTickResult(
                user_id=user_id,
                status=state.status,
                decision="skipped",
                reason="not_due",
                thoughts_used=state.thoughts_used,
            )
        context = await self.context_source.load(user_id, self.context_messages)
        last_user_at = context.last_user_message_at
        status = (
            PresenceStatus.ACTIVE
            if last_user_at is not None
            and current - last_user_at <= self.interaction_window
            else PresenceStatus.IDLE
        )
        if self.quiet_hours.is_quiet(user_id, current):
            status = PresenceStatus.SLEEPING

        state = self._with_activity(state, status, last_user_at, current)
        state = self._account_previous_outreach(state, context, current)
        self.repository.save_state(state)
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
        activity_result = await self._maybe_run_activity(
            state=state,
            user_id=user_id,
            last_user_at=last_user_at,
            now=current,
        )
        if activity_result is not None:
            return activity_result
        if state.thoughts_used >= self.daily_thought_budget:
            return self._finish(
                state,
                "skipped",
                "daily_budget",
                current,
                count_skip=True,
            )

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

        action_intent = _compact(draft.action_intent, 2000)
        action_request = _compact(draft.action_request, 200)
        if not action_intent and action_request:
            from features.agent.public import route_action_request

            action_intent = route_action_request(action_request)
            if not action_intent:
                self.repository.record_event(
                    user_id=user_id,
                    event_type="action_unavailable",
                    detail={"request": action_request},
                    now=current,
                )

        thought = PresenceThought(
            thought_id=f"thought_{uuid.uuid4().hex}",
            user_id=user_id,
            text=cleaned,
            salience=max(0.0, min(float(draft.salience), 1.0)),
            shareable=bool(draft.shareable),
            action_intent=action_intent,
            source_memory_id=memory.memory_id if memory else "",
            source_memory_text=_compact(memory.content, 500) if memory else "",
            plan=_compact(draft.plan, 200),
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
        if thought.salience >= self.memory_salience_threshold:
            try:
                memory_id = await self.memory_writer.remember(
                    user_id=user_id,
                    text=thought.text,
                    salience=thought.salience,
                )
                if memory_id:
                    self.repository.record_event(
                        user_id=user_id,
                        event_type="thought_memory_written",
                        detail={"thought_id": thought.thought_id, "memory_id": memory_id},
                        now=current,
                    )
            except Exception:
                logger.warning(
                    "Presence thought memory write failed user_id=%s",
                    user_id,
                    exc_info=True,
                )
        message_text = ""
        if (
            thought.shareable
            or thought.salience >= self.message_min_salience
            or thought.action_intent.strip()
        ):
            message_text = await self._maybe_create_goal(
                state=state,
                thought=thought,
                now=current,
            )
            if message_text:
                state = PresenceState(
                    **{
                        **state.__dict__,
                        "last_proactive_message_at": current,
                        "outreach_sent_count": state.outreach_sent_count + 1,
                        "outreach_last_counted_at": None,
                        "last_decision": "message",
                        "last_decision_reason": "proactive_message",
                        "last_tick_at": current,
                    }
                )
                self.repository.save_state(state)
        state = PresenceState(
            **{
                **state.__dict__,
                "next_tick_at": self._next_tick_at(
                    state,
                    current,
                    override_minutes=draft.next_wake_minutes,
                ),
                "consecutive_skips": (
                    0 if message_text else state.consecutive_skips + 1
                ),
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

    def _target_activity_tier(
        self,
        state: PresenceState,
        last_user_at: datetime | None,
        now: datetime,
    ) -> int:
        gap = now - last_user_at if last_user_at is not None else timedelta(0)
        if gap >= timedelta(hours=6):
            tier = 2
        elif gap >= timedelta(hours=2):
            tier = 1
        else:
            tier = 0
        if state.consecutive_l0 >= self.skip_threshold:
            tier = max(tier, 1)
        today = now.date()
        l2_today = state.l2_used if state.l2_budget_date == today else 0
        if tier >= 2 and l2_today >= self.l2_daily_limit:
            tier = 1
        return tier

    async def _maybe_run_activity(
        self,
        *,
        state: PresenceState,
        user_id: str,
        last_user_at: datetime | None,
        now: datetime,
    ) -> PresenceTickResult | None:
        """按 L0/L1/L2 挑一件议程活动；间隔越长越往高等级走。"""
        if state.status in {PresenceStatus.ACTIVE, PresenceStatus.SLEEPING}:
            return None
        from features.agent.public import actions_for_tier

        today = now.date()
        activities = state.activities_used if state.activity_budget_date == today else 0
        interval_ready = (
            state.last_activity_at is not None
            and now - state.last_activity_at >= self.activity_interval
        )
        forced = state.consecutive_skips >= self.skip_threshold
        target_tier = self._target_activity_tier(state, last_user_at, now)
        # 每第二次活动强制 L0，保证每天至少两次只写内部历史的自主活动。
        if (activities + 1) % 2 == 0:
            target_tier = 0
        should_run = (
            forced
            or (target_tier > 0 and interval_ready)
            or (activities < self.daily_activity_minimum and interval_ready)
        )
        if not should_run:
            return None
        self.repository.ensure_agenda(user_id, _DEFAULT_AGENDA)
        item = None
        tier = 0
        for candidate in (target_tier, 1, 0):
            item = self.repository.pick_agenda_item(
                user_id,
                actions_for_tier(candidate),
            )
            if item is not None:
                tier = candidate
                break
        if item is None:
            return None
        action_kind = item.action_kind or "reflect"
        try:
            goal_id = self.goal_creator.create_goal(
                user_id=user_id,
                intent=item.title,
                trigger_type="agenda",
                trigger_ref=item.item_id,
                action_intent=f"{action_kind}:{item.title}",
                plan=f"从议程做一件 L{tier} 活动：{item.title}",
            )
        except Exception:
            logger.warning(
                "Presence agenda goal failed user_id=%s",
                user_id,
                exc_info=True,
            )
            return None
        if not goal_id:
            return None
        state = PresenceState(
            **{
                **state.__dict__,
                "consecutive_skips": 0,
                "activities_used": activities + 1,
                "activity_budget_date": today,
                "last_activity_at": now,
                "consecutive_l0": (
                    state.consecutive_l0 + 1 if tier == 0 else 0
                ),
                "l2_used": (
                    (state.l2_used if state.l2_budget_date == today else 0)
                    + (1 if tier == 2 else 0)
                ),
                "l2_budget_date": today,
                "last_decision": "action",
                "last_decision_reason": "agenda_activity",
                "last_tick_at": now,
                "next_tick_at": self._next_tick_at(state, now),
            }
        )
        self.repository.save_state(state)
        self.repository.record_event(
            user_id=user_id,
            event_type="agenda_activity",
            detail={
                "item_id": item.item_id,
                "kind": item.kind,
                "tier": tier,
            },
            now=now,
        )
        return PresenceTickResult(
            user_id=user_id,
            status=state.status,
            decision="action",
            reason="agenda_activity",
            thoughts_used=state.thoughts_used,
        )

    async def _maybe_create_goal(
        self,
        *,
        state: PresenceState,
        thought: PresenceThought,
        now: datetime,
    ) -> str:
        intent_text = thought.action_intent.strip()
        if intent_text:
            from features.agent.public import get_action_spec, parse_action_kind

            if get_action_spec(parse_action_kind(intent_text)) is None:
                intent_text = ""
        if (
            not thought.shareable
            and thought.salience < self.message_min_salience
            and not intent_text
        ):
            # 既不想说话、也没有想做的事，就自己待着。
            return ""
        try:
            goal_id = self.goal_creator.create_goal(
                user_id=state.user_id,
                intent=thought.text,
                trigger_type="memory" if thought.source_memory_id else "presence",
                trigger_ref=thought.source_memory_id,
                action_intent=intent_text,
                plan=thought.plan,
            )
        except Exception:
            logger.warning(
                "Presence goal creation failed user_id=%s",
                state.user_id,
                exc_info=True,
            )
            self.repository.record_event(
                user_id=state.user_id,
                event_type="goal_creation_failed",
                detail={"thought_id": thought.thought_id},
                now=now,
            )
            return ""
        if not goal_id:
            # 48 小时去重命中：念头已经表达过，不再重复打扰。
            self.repository.record_event(
                user_id=state.user_id,
                event_type="goal_deduplicated",
                detail={"thought_id": thought.thought_id},
                now=now,
            )
            return ""
        self.repository.record_event(
            user_id=state.user_id,
            event_type="goal_created",
            detail={
                "thought_id": thought.thought_id,
                "goal_id": goal_id,
                "text": thought.text[:160],
            },
            now=now,
        )
        return thought.text

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

    def _account_previous_outreach(
        self,
        state: PresenceState,
        context,
        now: datetime,
    ) -> PresenceState:
        sent_at = state.last_proactive_message_at
        if sent_at is None or state.outreach_last_counted_at == sent_at:
            return state
        if (
            context.last_user_message_at is not None
            and context.last_user_message_at > sent_at
        ):
            return PresenceState(
                **{
                    **state.__dict__,
                    "outreach_replied_count": state.outreach_replied_count + 1,
                    "consecutive_unanswered": 0,
                    "outreach_downshift_until": None,
                    "outreach_last_counted_at": sent_at,
                }
            )
        if now - sent_at < timedelta(hours=2):
            return state
        unanswered = state.consecutive_unanswered + 1
        return PresenceState(
            **{
                **state.__dict__,
                "consecutive_unanswered": unanswered,
                "outreach_last_counted_at": sent_at,
                "outreach_downshift_until": (
                    now + timedelta(days=7) if unanswered >= 2 else state.outreach_downshift_until
                ),
            }
        )

    def _with_activity(self, state, status, last_user_at, now) -> PresenceState:
        return PresenceState(
            **{
                **state.__dict__,
                "status": status,
                "last_user_message_at": last_user_at,
                "last_tick_at": now,
            }
        )

    def _next_tick_at(
        self,
        state,
        now: datetime,
        override_minutes: int = 0,
    ) -> datetime:
        if (
            state.outreach_downshift_until is not None
            and now < state.outreach_downshift_until
        ):
            return now + self.downshift_interval
        if override_minutes:
            minutes = max(
                self.min_wake_minutes,
                min(int(override_minutes), self.max_wake_minutes),
            )
            return now + timedelta(minutes=minutes)
        if state.status == PresenceStatus.ACTIVE:
            base = self.active_interval
        elif state.status == PresenceStatus.SLEEPING:
            base = self.sleeping_interval
        else:
            base = self.idle_interval
        return now + self._reply_adjusted(base, state)

    def _reply_adjusted(self, base, state) -> timedelta:
        sent = state.outreach_sent_count
        replied = state.outreach_replied_count
        if sent < 3:
            return base
        rate = replied / sent
        if rate < 0.2:
            return base * 2
        if rate < 0.5:
            return base + timedelta(minutes=30)
        return base

    def _finish(
        self,
        state,
        decision: str,
        reason: str,
        now,
        *,
        count_skip: bool = False,
    ) -> PresenceTickResult:
        updates = {
            "last_decision": decision,
            "last_decision_reason": reason,
            "last_tick_at": now,
            "next_tick_at": self._next_tick_at(state, now),
        }
        if count_skip:
            updates["consecutive_skips"] = state.consecutive_skips + 1
        state = PresenceState(**{**state.__dict__, **updates})
        self.repository.save_state(state)
        self.repository.record_event(
            user_id=state.user_id,
            event_type="tick",
            detail={
                "decision": decision,
                "reason": reason,
                "status": state.status,
            },
            now=now,
        )
        return PresenceTickResult(
            user_id=state.user_id,
            status=state.status,
            decision=decision,
            reason=reason,
            thoughts_used=state.thoughts_used,
        )
