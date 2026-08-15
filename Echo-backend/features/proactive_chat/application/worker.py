from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from features.agent.domain.delivery import AgentDeliveryPlanError, validate_agent_delivery_segments
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
    ):
        self.repository = repository
        self.reply_generator = reply_generator
        self.request_guard = request_guard
        self.event_broker = event_broker
        self.timing_policy = timing_policy
        self.lease_seconds = lease_seconds

    async def run_once(self) -> bool:
        job = self.repository.claim_due_job(self.lease_seconds)
        if job is None:
            return self.repository.create_spontaneous_job_if_due()
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
            delivery_types = ["text" for _ in prepared.reply_segments]
            if any(part.type == "sticker" for part in prepared.content_parts):
                if prepared.sticker_placement == "before_text":
                    delivery_types.insert(0, "sticker")
                else:
                    delivery_types.append("sticker")
            presentation = self.timing_policy.build(
                delivery_types=tuple(delivery_types or ["text"]),
                agent_elapsed_ms=int((time.perf_counter() - started) * 1000),
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
