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
from features.chat.domain.services import ChatRequestGuard
from features.chat.infrastructure.events import ChatEvent, ChatEventBroker
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)

logger = logging.getLogger(__name__)


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
        allow_spontaneous_jobs: bool = True,
    ):
        self.repository = repository
        self.reply_generator = reply_generator
        self.request_guard = request_guard
        self.event_broker = event_broker
        self.timing_policy = timing_policy
        self.lease_seconds = lease_seconds
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
            delivery_types = [
                item.message_type
                for item in build_delivery_items(
                    prepared.reply_segments,
                    tuple(
                        part
                        for part in prepared.content_parts
                        if part.type == "sticker"
                    ),
                    prepared.sticker_placement,
                )
            ]
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
            budget = {"quiet": 1, "standard": 6, "active": 12}.get(level, 6)
            if self.repository.count_goals_reported_today(goal.user_id) >= budget:
                self.repository.suppress_job(job.job_id, "daily_budget")
                self.repository.mark_goal_failed(
                    goal.goal_id,
                    result_summary=f"当日主动预算已用尽（{level}）",
                )
                return True

            draft = goal.draft_text.strip()
            if goal.action_intent.strip():
                segments, result_status, result_summary = await self._execute_goal_actions(
                    goal,
                    conversation_id,
                )
            else:
                segments = (draft,) if draft else ()
                result_status, result_summary = "success", ""
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
        from features.agent.public import run_chat_agent

        fallback = f"本来想{goal.intent[:40]}，这次没做成。"
        instruction = (
            f"这是你自己的主动念头，不是用户发来的新消息：{goal.intent}\n"
            f"你原本倾向做的事：{goal.action_intent or '只是想说句话'}\n"
            "可以照这个倾向做，也可以根据当下判断换一件更合适的事，或者只发一句话。"
            "如果做了动作，做完就用一两句自然的话告诉用户你做了什么、结果如何；"
            "没做成或只完成一部分，就如实说，不要假装完成。"
            "不要提工具名、系统、调度或内部流程。"
        )
        try:
            result = await run_chat_agent(
                user_id=goal.user_id,
                message=instruction,
                messages=[
                    {"role": "system", "content": "这是一次主动执行，不是用户消息。"},
                ],
                conversation_id=conversation_id,
                conversation_mode="proactive",
                tools_enabled=True,
            )
        except Exception as exc:
            return (fallback,), "failed", f"主动执行异常：{type(exc).__name__}"

        segments = result.reply_segments or (
            (result.reply_text,) if result.reply_text.strip() else ()
        )
        if result.status != AgentRunStatus.COMPLETED or not segments:
            return (fallback,), "failed", f"主动执行未完成：{result.error_code or 'empty_reply'}"

        failed_tools = [
            tool_result.tool_name
            for tool_result in result.tool_results
            if tool_result.status in {AgentToolStatus.FAILED, AgentToolStatus.TIMED_OUT}
        ]
        if failed_tools:
            return tuple(segments), "partial", "部分动作失败：" + ",".join(failed_tools)
        return tuple(segments), "success", ""

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
