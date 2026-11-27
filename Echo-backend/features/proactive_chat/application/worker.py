from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from features.agent.domain.delivery import (
    AgentDeliveryPlanError,
    build_delivery_items,
    validate_agent_delivery_segments,
)
from features.agent.domain.entities import AgentRunStatus, AgentToolStatus
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.delivery_timing import DeliveryTimingPolicy
from features.chat.domain.dialogue_style import guard_dialogue_reply
from features.chat.domain.services import ChatRequestGuard
from features.chat.infrastructure.events import ChatEvent, ChatEventBroker
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)

logger = logging.getLogger(__name__)

# Echo 在虚拟机小号上看到的主号联系人名
_WECHAT_NOTIFY_TARGET = "叶子"


def _iso_to_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class ProcessProactiveChatJobs:
    def __init__(
        self,
        *,
        repository: PostgresProactiveChatRepository,
        reply_generator: GenerateChatReply,
        request_guard: ChatRequestGuard,
        event_broker: ChatEventBroker,
        timing_policy: DeliveryTimingPolicy,
        lease_seconds: int,
        daily_budget: int = 20,
        allow_spontaneous_jobs: bool = True,
    ):
        self.repository = repository
        self.reply_generator = reply_generator
        self.request_guard = request_guard
        self.event_broker = event_broker
        self.timing_policy = timing_policy
        self.lease_seconds = lease_seconds
        self.daily_budget = daily_budget
        self.allow_spontaneous_jobs = allow_spontaneous_jobs

    async def run_once(self) -> bool:
        job = self.repository.claim_due_job(self.lease_seconds)
        if job is None:
            if not self.allow_spontaneous_jobs:
                return False
            return self.repository.create_spontaneous_job_if_due()
        if job.goal_id is not None:
            return await self._deliver_goal_job(job)
        if job.schedule_id is None and not self.allow_spontaneous_jobs:
            self.repository.suppress_job(job.job_id, "presence_owns_spontaneous")
            return True
        if not self.request_guard.try_acquire(job.user_id):
            self.repository.defer_job_to(
                job.job_id,
                datetime.now(UTC) + timedelta(seconds=1),
                "chat_busy",
            )
            return True

        try:
            preference, schedule, conversation_id = self.repository.load_job_context(job)
            if job.schedule_id is not None and schedule is None:
                self.repository.suppress_job(job.job_id, "schedule_deleted")
                return True
            if schedule is not None and schedule.status != "active":
                self.repository.suppress_job(job.job_id, "schedule_inactive")
                return True
            explicit = schedule is not None and schedule.created_by == "user_request"
            if not preference.enabled and not explicit:
                self.repository.suppress_job(job.job_id, "proactive_disabled")
                return True
            if schedule is None and not preference.allow_spontaneous_chat:
                self.repository.suppress_job(job.job_id, "spontaneous_disabled")
                return True
            if (
                (schedule is None or schedule.created_by == "echo_agent")
                and preference.pause_indefinite
            ):
                self.repository.suppress_job(job.job_id, "proactive_paused")
                return True
            if (
                (schedule is None or schedule.created_by == "echo_agent")
                and preference.paused_until is not None
                and preference.paused_until > datetime.now(UTC)
            ):
                self.repository.suppress_job(job.job_id, "proactive_paused")
                return True
            if (
                schedule is not None
                and schedule.created_by == "echo_agent"
                and not preference.allow_echo_scheduling
            ):
                self.repository.suppress_job(job.job_id, "echo_scheduling_disabled")
                return True
            if (
                schedule is None or schedule.created_by == "echo_agent"
            ) and preference.consecutive_unanswered >= 2:
                self.repository.suppress_job(job.job_id, "unanswered_pause")
                return True
            if self._suppress_changed_spontaneous_job(job, schedule, "before_generation"):
                return True

            now = datetime.now(UTC)
            if self.repository.is_quiet(preference, now) and not (
                explicit and preference.explicit_reminder_quiet_policy == "honor"
            ):
                self.repository.defer_job_to(
                    job.job_id,
                    self.repository.quiet_end_after(preference, now),
                    "quiet_hours",
                )
                return True

            intent = (
                schedule.intent
                if schedule is not None
                else "Start a natural, low-pressure check-in if it is genuinely appropriate."
            )
            prompt = (
                "This is a system-generated proactive trigger, not an incoming user message. "
                "No current user activity has been observed. Use the following intent as "
                f"internal context only: {intent}. Do not mention schedules, workers, "
                "notifications, or that you were waiting. Do not state or imply that the "
                "user is awake, online, reading, responding, energetic, available, or "
                "currently doing something unless verified by an actual user message. "
                "Phrase uncertain current-state references conditionally, such as asking "
                "them to reply after they wake up or when they are free. "
                "If no natural message is appropriate, return no user-visible text."
            )
            started = time.perf_counter()
            try:
                prepared = await self.reply_generator.prepare(
                    user_id=job.user_id,
                    message=prompt,
                    conversation_id=conversation_id,
                    conversation_mode="proactive",
                    proactive_intent=(schedule.intent if schedule is not None else ""),
                    proactive_force_send=explicit,
                )
                validate_agent_delivery_segments(prepared.reply_segments)
            except AgentDeliveryPlanError:
                self.repository.suppress_job(job.job_id, "agent_output_rejected")
                logger.warning(
                    "Proactive chat job suppressed job_id=%s reason=agent_output_rejected",
                    job.job_id,
                    exc_info=True,
                )
                return True
            if self._suppress_changed_spontaneous_job(job, schedule, "before_persistence"):
                return True
            duplicate_checker = getattr(self.repository, "has_recent_assistant_content", None)
            if (
                schedule is None
                and callable(duplicate_checker)
                and duplicate_checker(
                    job.user_id,
                    conversation_id,
                    prepared.reply_segments,
                )
            ):
                self.repository.suppress_job(job.job_id, "duplicate_delivery")
                logger.info(
                    "Proactive chat job suppressed job_id=%s reason=duplicate_delivery",
                    job.job_id,
                )
                return True
            if not prepared.reply_segments and not prepared.content_parts:
                reason = (
                    (
                        prepared.error_code
                        if prepared.error_code.startswith("planner_")
                        else f"agent_failed:{prepared.error_code}"
                    )
                    if prepared.error_code
                    else "agent_skip"
                )
                self.repository.suppress_job(job.job_id, reason)
                logger.warning(
                    "Proactive chat job suppressed job_id=%s reason=%s",
                    job.job_id,
                    reason,
                )
                return True
            delivery_items = build_delivery_items(
                prepared.reply_segments,
                tuple(
                    part
                    for part in prepared.content_parts
                    if part.type == "sticker"
                ),
                prepared.sticker_placement,
            )
            delivery_types = [item.message_type for item in delivery_items]
            presentation = self.timing_policy.build(
                delivery_types=tuple(delivery_types or ["text"]),
                agent_elapsed_ms=int((time.perf_counter() - started) * 1000),
                text_segments=prepared.reply_segments,
            )
            messages = self.repository.persist_delivery(
                job=job,
                preference=preference,
                schedule=schedule,
                conversation_id=conversation_id,
                reply_segments=prepared.reply_segments,
                content_parts=prepared.content_parts,
                sticker_placement=prepared.sticker_placement,
                agent_turn_id=prepared.run_id,
            )
            if not messages:
                return True
            self._record_delivery_events(job.user_id, conversation_id, messages)
            # 主动消息优先走微信：App 侧照常记录，微信是主要触达渠道
            from features.desktop.public import send_wechat_delivery

            try:
                await send_wechat_delivery(
                    user_id=job.user_id,
                    items=delivery_items,
                )
            except Exception:
                logger.warning(
                    "Proactive WeChat delivery failed job_id=%s",
                    job.job_id,
                    exc_info=True,
                )
            await self.event_broker.publish(
                job.user_id,
                ChatEvent(
                    event="chat.delivery.created",
                    data={
                        "turn_id": job.job_id,
                        "reply_group_id": f"proactive_{job.job_id}",
                        "conversation_id": conversation_id,
                        "origin": "proactive",
                        "trigger_id": schedule.schedule_id if schedule else job.job_id,
                        "presentation": {
                            "agent_elapsed_ms": presentation.agent_elapsed_ms,
                            "initial_delay_ms": presentation.initial_delay_ms,
                            "message_delays_ms": list(presentation.message_delays_ms),
                        },
                        "messages": messages,
                    },
                ),
            )
            logger.info(
                "Proactive chat job delivered job_id=%s messages=%s", job.job_id, len(messages)
            )
            return True
        except Exception as exc:
            self.repository.fail_job(job, type(exc).__name__)
            logger.exception("Proactive chat job failed job_id=%s", job.job_id)
            return True
        finally:
            self.request_guard.release(job.user_id)

    @staticmethod
    def _record_delivery_events(
        user_id: str,
        conversation_id: str,
        messages: list[dict[str, object]],
    ) -> None:
        """主动消息不经过聊天用例，这里补写统一事件流。"""
        from features.conversation_events.public import (
            ACTOR_ECHO,
            EVENT_MESSAGE,
            record_conversation_event,
        )

        try:
            for message in messages:
                record_conversation_event(
                    event_type=EVENT_MESSAGE,
                    source="proactive",
                    actor=ACTOR_ECHO,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    content=str(message.get("content") or ""),
                    payload={
                        "message_id": message.get("message_id"),
                        "message_type": message.get("message_type"),
                        "reply_group_id": message.get("reply_group_id"),
                    },
                    source_created_at=_iso_to_datetime(message.get("created_at")),
                )
        except Exception:
            logger.warning("record proactive delivery events failed", exc_info=True)

    async def _deliver_goal_job(self, job) -> bool:
        """投递 presence 产出的目标：文案已经在生成念头时写好，这里只做门禁与投递。"""
        goal = self.repository.get_goal(job.goal_id)
        if goal is None:
            self.repository.suppress_job(job.job_id, "goal_missing")
            return True
        if not self.request_guard.try_acquire(job.user_id):
            self.repository.defer_job_to(
                job.job_id,
                datetime.now(UTC) + timedelta(seconds=1),
                "chat_busy",
            )
            return True

        try:
            preference, _schedule, conversation_id = self.repository.load_job_context(job)
            if not preference.enabled:
                self.repository.suppress_job(job.job_id, "proactive_disabled")
                self.repository.mark_goal_failed(goal.goal_id)
                return True
            if preference.pause_indefinite or (
                preference.paused_until is not None
                and preference.paused_until > datetime.now(UTC)
            ):
                self.repository.suppress_job(job.job_id, "proactive_paused")
                self.repository.mark_goal_failed(goal.goal_id)
                return True
            now = datetime.now(UTC)
            if self.repository.is_quiet(preference, now):
                self.repository.defer_job_to(
                    job.job_id,
                    self.repository.quiet_end_after(preference, now),
                    "quiet_hours",
                )
                return True

            # 三档预算：quiet 1 / standard 6 / active 12（按当日已投递目标计）。
            level = getattr(preference, "proactivity_level", "standard") or "standard"
            budget = self.daily_budget
            if self.repository.count_goals_reported_today(goal.user_id) >= budget:
                self.repository.suppress_job(job.job_id, "daily_budget")
                self.repository.mark_goal_failed(
                    goal.goal_id,
                    result_summary=f"当日主动预算已用尽（{level}）",
                )
                return True

            has_action = bool(goal.action_intent.strip())
            pure_action = has_action
            if has_action:
                segments, result_status, result_summary = await self._execute_goal_actions(
                    goal,
                    conversation_id,
                )
            else:
                prepared = await self.reply_generator.prepare(
                    user_id=job.user_id,
                    message=goal.intent,
                    conversation_id=conversation_id,
                    conversation_mode="proactive",
                    proactive_intent=goal.intent,
                    proactive_plan=goal.plan,
                    proactive_force_send=True,
                    proactive_skip_planner=True,
                    proactive_brief=goal.intent,
                )
                if prepared.error_code:
                    self.repository.suppress_job(job.job_id, "agent_output_rejected")
                    self.repository.mark_goal_failed(goal.goal_id)
                    logger.info(
                        "Proactive chat job suppressed job_id=%s "
                        "reason=agent_output_rejected code=%s",
                        job.job_id,
                        prepared.error_code,
                    )
                    return True
                segments = prepared.reply_segments
                result_status, result_summary = "success", ""
            if pure_action:
                # L0 只写内部历史；L1/L2 才接触用户。
                from features.agent.public import get_action_spec, parse_action_kind

                spec = get_action_spec(parse_action_kind(goal.action_intent))
                tier = spec.tier if spec is not None else 0
                note = " ".join(segment.strip() for segment in segments if segment.strip())
                if not note:
                    note = f"做了{goal.action_intent[:40]}，没有更多细节。"
                if tier > 0:
                    from features.chat.public import deliver_external_assistant_message
                    from features.desktop.public import send_wechat_message

                    try:
                        await send_wechat_message(
                            user_id=job.user_id,
                            chat=_WECHAT_NOTIFY_TARGET,
                            text=note,
                        )
                    except Exception:
                        logger.warning("activity delivery failed", exc_info=True)
                    try:
                        await deliver_external_assistant_message(
                            user_id=job.user_id,
                            content=note,
                            idempotency_key=f"agenda_action:{goal.goal_id}",
                            source="presence",
                        )
                    except Exception:
                        logger.warning("activity history failed", exc_info=True)
                else:
                    try:
                        from features.chat.public import record_internal_assistant_note

                        record_internal_assistant_note(
                            user_id=job.user_id,
                            conversation_id=conversation_id,
                            content=note,
                            source="presence_action",
                        )
                    except Exception:
                        logger.warning("record pure action note failed", exc_info=True)
                self.repository.mark_goal_reported(
                    goal.goal_id,
                    result_status=result_status,
                    result_summary=result_summary,
                )
                logger.info(
                    "Proactive pure action done job_id=%s goal_id=%s status=%s",
                    job.job_id,
                    goal.goal_id,
                    result_status,
                )
                return True
            if not any(segment.strip() for segment in segments):
                self.repository.suppress_job(job.job_id, "empty_goal")
                self.repository.mark_goal_failed(goal.goal_id, result_summary=result_summary)
                return True
            segments = tuple(segment.strip() for segment in segments if segment.strip())

            presentation = self.timing_policy.build(
                delivery_types=("text",),
                agent_elapsed_ms=0,
                text_segments=segments,
            )
            messages = self.repository.persist_delivery(
                job=job,
                preference=preference,
                schedule=None,
                conversation_id=conversation_id,
                reply_segments=segments,
                content_parts=(),
                sticker_placement="after_text",
                agent_turn_id=goal.goal_id,
            )
            if not messages:
                self.repository.suppress_job(job.job_id, "goal_persist_failed")
                self.repository.mark_goal_failed(goal.goal_id)
                return True
            self._record_delivery_events(job.user_id, conversation_id, messages)
            await self.event_broker.publish(
                job.user_id,
                ChatEvent(
                    event="chat.delivery.created",
                    data={
                        "turn_id": job.job_id,
                        "reply_group_id": f"goal_{job.job_id}",
                        "conversation_id": conversation_id,
                        "origin": "presence",
                        "trigger_id": goal.goal_id,
                        "presentation": {
                            "agent_elapsed_ms": presentation.agent_elapsed_ms,
                            "initial_delay_ms": presentation.initial_delay_ms,
                            "message_delays_ms": list(presentation.message_delays_ms),
                        },
                        "messages": messages,
                    },
                ),
            )
            self.repository.mark_goal_reported(
                goal.goal_id,
                result_status=result_status,
                result_summary=result_summary,
            )
            logger.info(
                "Proactive goal delivered job_id=%s goal_id=%s result=%s",
                job.job_id,
                goal.goal_id,
                result_status,
            )
            return True
        except Exception as exc:
            self.repository.fail_job(job, type(exc).__name__)
            self.repository.mark_goal_failed(goal.goal_id)
            logger.exception("Proactive goal job failed job_id=%s", job.job_id)
            return True
        finally:
            self.request_guard.release(job.user_id)

    async def _execute_goal_actions(
        self,
        goal,
        conversation_id: str,
    ) -> tuple[tuple[str, ...], str, str]:
        """给模型一次主动机会：可以照念头做，也可以换个更有理由的动作。

        `action_intent` 只是倾向，不是命令；代码只负责判断结果、兜底和记账。
        """
        from features.agent.public import (
            get_action_spec,
            parse_action_kind,
            run_chat_agent,
        )
        from features.chat.public import build_proactive_writer_messages

        spec = get_action_spec(parse_action_kind(goal.action_intent))
        tool_scope = spec.tool_scope if spec is not None else None
        messages = await build_proactive_writer_messages(
            user_id=goal.user_id,
            conversation_id=conversation_id,
            brief=goal.intent,
            plan=goal.plan,
            action_intent=goal.action_intent,
        )
        if not messages:
            return (), "failed", "主动动作提示缺失"
        try:
            result = await run_chat_agent(
                user_id=goal.user_id,
                message="根据后端批准的主动聊天安全摘要生成自然正文。",
                messages=messages,
                conversation_id=conversation_id,
                conversation_mode="proactive",
                tools_enabled=True,
                tool_scope=tool_scope,
            )
        except Exception as exc:
            return (), "failed", f"主动执行异常：{type(exc).__name__}"

        segments = result.reply_segments or (
            (result.reply_text,) if result.reply_text.strip() else ()
        )
        if result.status != AgentRunStatus.COMPLETED or not segments:
            return (), "failed", f"主动执行未完成：{result.error_code or 'empty_reply'}"

        guarded_segments: list[str] = []
        for segment in segments:
            cleaned, _violations = guard_dialogue_reply(
                segment,
                goal.intent,
                allow_empty=True,
            )
            if cleaned.strip():
                guarded_segments.append(cleaned.strip())
        if not guarded_segments:
            return (), "failed", "风格检查后为空"

        failed_tools = [
            tool_result.tool_name
            for tool_result in result.tool_results
            if tool_result.status in {AgentToolStatus.FAILED, AgentToolStatus.TIMED_OUT}
        ]
        if failed_tools:
            return (
                tuple(guarded_segments),
                "partial",
                "部分动作失败：" + ",".join(failed_tools),
            )
        return tuple(guarded_segments), "success", ""

    def _suppress_changed_spontaneous_job(self, job, schedule, phase: str) -> bool:
        if schedule is not None or not self.repository.spontaneous_job_context_changed(job):
            return False
        self.repository.suppress_job(job.job_id, "spontaneous_context_changed")
        logger.info(
            "Proactive chat job suppressed job_id=%s reason=spontaneous_context_changed "
            "phase=%s",
            job.job_id,
            phase,
        )
        return True
