import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable

from features.agent.domain.delivery import (
    build_natural_delivery_plan,
    validate_agent_delivery_segments,
)
from features.agent.domain.entities import ContentPart, ProactiveAction, ProactiveDecision
from features.agent.domain.services import ProactiveDecisionPlanner, ProactivePlannerError
from features.chat.application.call_reply_limiter import CallReplyStreamLimiter
from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.domain.entities import (
    CHAT_CHANNEL_APP,
    CHAT_VISIBILITY_MAIN,
    ChatTurnResult,
    ChatValidationError,
    MemoryExtractionScheduleResult,
    PreparedChatReply,
)
from features.chat.domain.repositories import ChatConversationRepository
from features.chat.domain.services import (
    ChatAgentOrchestrator,
    ChatContextProvider,
    ConversationSummaryUpdater,
    MemoryExtractionScheduler,
    RelationshipTurnRecorder,
)

logger = logging.getLogger(__name__)


class GenerateChatReply:
    """Application use case for one complete chat turn."""

    def __init__(
        self,
        conversation_repository: ChatConversationRepository,
        context_provider: ChatContextProvider,
        summary_updater: ConversationSummaryUpdater,
        memory_scheduler: MemoryExtractionScheduler,
        relationship_recorder: RelationshipTurnRecorder | None = None,
        agent_orchestrator: ChatAgentOrchestrator | None = None,
        proactive_planner: ProactiveDecisionPlanner | None = None,
        summary_update_in_background: bool = False,
        call_reply_max_chars: int = 80,
    ):
        self.conversation_repository = conversation_repository
        self.context_provider = context_provider
        self.summary_updater = summary_updater
        self.memory_scheduler = memory_scheduler
        self.relationship_recorder = relationship_recorder
        self.agent_orchestrator = agent_orchestrator
        self.proactive_planner = proactive_planner
        self.summary_update_in_background = summary_update_in_background
        self.call_reply_max_chars = call_reply_max_chars
        self._summary_tasks: set[asyncio.Task[bool]] = set()

    async def _update_summary(self, user_id: str, conversation_id: str) -> bool:
        started_at = time.perf_counter()
        try:
            updated = await self.summary_updater.maybe_update_summary(user_id, conversation_id)
            logger.info(
                "Conversation summary check completed updated=%s duration_ms=%.1f",
                updated,
                (time.perf_counter() - started_at) * 1000,
            )
            return updated
        except Exception:
            logger.exception(
                "Conversation summary update failed for conversation_id=%s duration_ms=%.1f",
                conversation_id,
                (time.perf_counter() - started_at) * 1000,
            )
            return False

    def _schedule_summary_update(self, user_id: str, conversation_id: str) -> None:
        task = asyncio.create_task(self._update_summary(user_id, conversation_id))
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)

    async def _complete_turn(
        self,
        clean_user_id: str,
        clean_message: str,
        resolved_conversation_id: str,
        reply: str,
        user_message_type: str,
        assistant_message_type: str,
        user_content_parts: tuple[ContentPart, ...],
        assistant_content_parts: tuple[ContentPart, ...],
        channel: str,
        visibility: str,
        reply_segments: tuple[str, ...] = (),
        sticker_placement: str = "after_text",
        memory_enabled: bool = True,
    ) -> ChatTurnResult:
        user_message_id, assistant_message_id = self.conversation_repository.add_chat_turn(
            user_id=clean_user_id,
            conversation_id=resolved_conversation_id,
            user_message=clean_message,
            assistant_reply=reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
            user_content_parts=user_content_parts,
            assistant_content_parts=assistant_content_parts,
            channel=channel,
            visibility=visibility,
        )

        summary_updated, memory_gate = await self._run_post_persistence(
            clean_user_id=clean_user_id,
            clean_message=clean_message,
            resolved_conversation_id=resolved_conversation_id,
            reply=reply,
            source_message_id=user_message_id,
            memory_enabled=memory_enabled,
        )

        return ChatTurnResult(
            reply=reply,
            user_message=clean_message,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            conversation_id=resolved_conversation_id,
            summary_updated=summary_updated,
            memory_extraction_scheduled=memory_gate.should_extract,
            memory_extraction_gate_reason=memory_gate.reason,
            memory_extraction_job_id=memory_gate.job_id,
            reply_segments=reply_segments,
            sticker_placement=sticker_placement,
        )

    async def _run_post_persistence(
        self,
        *,
        clean_user_id: str,
        clean_message: str,
        resolved_conversation_id: str,
        reply: str,
        source_message_id: int,
        memory_enabled: bool = True,
    ) -> tuple[bool, MemoryExtractionScheduleResult]:
        if not memory_enabled:
            return False, MemoryExtractionScheduleResult(
                should_extract=False,
                reason="speaker_unknown",
            )
        summary_updated = False
        if self.summary_update_in_background:
            self._schedule_summary_update(clean_user_id, resolved_conversation_id)
        else:
            summary_updated = await self._update_summary(
                clean_user_id,
                resolved_conversation_id,
            )

        user_message_count = self.conversation_repository.count_user_messages(
            clean_user_id,
            resolved_conversation_id,
        )
        candidate_user_messages = self.conversation_repository.list_recent_user_messages(
            clean_user_id,
            resolved_conversation_id,
            limit=5,
        )
        memory_gate = self.memory_scheduler.schedule(
            user_id=clean_user_id,
            user_message=clean_message,
            assistant_reply=reply,
            source_message_id=source_message_id,
            candidate_user_messages=candidate_user_messages,
            force_batch_review=(user_message_count % 5 == 0),
        )

        if self.relationship_recorder is not None:
            relationship_recorded = self.relationship_recorder.record(
                user_id=clean_user_id,
                user_message=clean_message,
                source_message_id=source_message_id,
            )
            if not relationship_recorded:
                logger.warning("Relationship turn recording skipped for user_id=%s", clean_user_id)

        return summary_updated, memory_gate

    async def finalize_persisted_turn(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: int,
        memory_enabled: bool = True,
    ) -> None:
        await self._run_post_persistence(
            clean_user_id=user_id,
            clean_message=user_message,
            resolved_conversation_id=conversation_id,
            reply=assistant_reply,
            source_message_id=source_message_id,
            memory_enabled=memory_enabled,
        )

    async def prepare(
        self,
        *,
        user_id: str,
        message: str,
        conversation_id: str,
        conversation_mode: str = "chat",
        sticker_intent: str = "",
        history_before_message_id: int | None = None,
        proactive_intent: str = "",
        proactive_force_send: bool = False,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
        tools_enabled: bool | None = None,
        speaker_role: str | None = None,
        speaker_confidence: float = 0.0,
        memory_enabled: bool = True,
    ) -> PreparedChatReply:
        clean_user_id = user_id.strip()
        clean_message = message.strip()
        if not clean_user_id:
            raise ChatValidationError("Missing user_id")
        if not clean_message:
            raise ChatValidationError("Empty message")

        context_started_at = time.perf_counter()
        context_kwargs = {}
        if speaker_role is not None:
            context_kwargs["speaker_role"] = speaker_role
        if not memory_enabled:
            context_kwargs["memory_enabled"] = False
        if history_before_message_id is None:
            context = await self.context_provider.build_context(
                clean_user_id,
                clean_message,
                conversation_id,
                conversation_mode,
                **context_kwargs,
            )
        else:
            context = await self.context_provider.build_context(
                clean_user_id,
                clean_message,
                conversation_id,
                conversation_mode,
                history_before_message_id=history_before_message_id,
                **context_kwargs,
            )
        if self.agent_orchestrator is None:
            raise RuntimeError("Unified Agent runtime is not configured")
        if speaker_role:
            context.messages.append(
                {
                    "role": "system",
                    "content": (
                        f"当前设备声纹判断：{speaker_role}，置信度 {max(0.0, min(1.0, speaker_confidence)):.2f}。"
                        if speaker_role == "owner"
                        else "当前设备声纹未确认主人身份。"
                    ),
                }
            )
        agent_messages = context.messages
        agent_message = clean_message
        call_reply_limiter: CallReplyStreamLimiter | None = None
        effective_on_text_delta = on_text_delta
        if conversation_mode == "call":
            async def deliver_call_delta(delta: str) -> None:
                validate_agent_delivery_segments((delta,))
                if on_text_delta is not None:
                    await on_text_delta(delta)

            call_reply_limiter = CallReplyStreamLimiter(
                max_chars=self.call_reply_max_chars,
                on_text_delta=deliver_call_delta,
            )
            effective_on_text_delta = call_reply_limiter.push
        if conversation_mode == "proactive" and self.proactive_planner is not None:
            safe_facts = dict(context.proactive_safe_facts)
            clean_intent = proactive_intent.strip().replace("\r", " ").replace("\n", " ")[:240]
            if clean_intent:
                safe_facts["task_intent"] = f"后端确认的主动任务目的：{clean_intent}"
            try:
                decision = await self.proactive_planner.decide(
                    context.messages,
                    tuple(safe_facts),
                    force_send=proactive_force_send,
                )
            except ProactivePlannerError as exc:
                logger.warning("Proactive planner technical failure code=%s", exc.code)
                return PreparedChatReply(
                    reply="",
                    reply_segments=(),
                    error_code=exc.code,
                )
            logger.info(
                "Proactive planner completed action=%s topic=%s tone=%s facts=%s reason=%s",
                decision.action,
                decision.topic,
                decision.tone,
                ",".join(decision.safe_fact_ids),
                decision.reason,
            )
            if decision.action == ProactiveAction.SKIP:
                return PreparedChatReply(reply="", reply_segments=())
            if not context.proactive_writer_messages:
                logger.error("Proactive writer context missing; suppressing delivery")
                return PreparedChatReply(reply="", reply_segments=())
            agent_messages = self._build_proactive_writer_turn(
                context.proactive_writer_messages,
                safe_facts,
                decision,
            )
            agent_message = "根据后端批准的主动聊天安全摘要生成自然正文。"
        agent_kwargs = {
            "conversation_mode": conversation_mode,
            "sticker_intent": sticker_intent,
            "allow_proactive_stickers": context.allow_proactive_stickers,
            "proactive_sticker_due": context.proactive_sticker_due,
        }
        if "conversation_id" in inspect.signature(self.agent_orchestrator.run).parameters:
            agent_kwargs["conversation_id"] = conversation_id
        if "on_text_delta" in inspect.signature(self.agent_orchestrator.run).parameters:
            agent_kwargs["on_text_delta"] = effective_on_text_delta
        if "on_progress_text" in inspect.signature(self.agent_orchestrator.run).parameters:
            agent_kwargs["on_progress_text"] = on_progress_text
        if "tools_enabled" in inspect.signature(self.agent_orchestrator.run).parameters:
            agent_kwargs["tools_enabled"] = tools_enabled
        agent_result = await self.agent_orchestrator.run(
            clean_user_id,
            agent_message,
            agent_messages,
            **agent_kwargs,
        )
        logger.info(
            "Chat reply prepared duration_ms=%.1f",
            (time.perf_counter() - context_started_at) * 1000,
        )
        if conversation_mode == "call" and call_reply_limiter is not None:
            limited_reply = await call_reply_limiter.finish(agent_result.reply_text)
            if call_reply_limiter.truncated:
                logger.info(
                    "Call reply truncated at natural delivery boundary "
                    "observed_chars=%s delivered_chars=%s max_chars=%s",
                    call_reply_limiter.observed_chars,
                    len(limited_reply),
                    self.call_reply_max_chars,
                )
            delivery_plan = build_natural_delivery_plan(
                limited_reply,
                conversation_mode,
            )
            segments = delivery_plan.text_segments
        else:
            segments = tuple(
                segment.strip()
                for segment in agent_result.reply_segments
                if segment.strip()
            )
            if not segments and agent_result.reply_text.strip():
                segments = (agent_result.reply_text.strip(),)
        reply = "\n".join(segments)
        if conversation_mode != "call":
            style_violations = find_dialogue_style_violations(
                reply,
                clean_message,
                pause_followup_questions=context.pause_followup_questions,
                suppress_repeated_greeting=context.suppress_repeated_greeting,
                grounded_weekday=str(context.temporal_context.get("weekday") or ""),
            )
            if style_violations:
                logger.warning(
                    "Dialogue style fallback applied violation_types=%s",
                    ",".join(style_violations),
                )
                reply = apply_dialogue_fallback(
                    reply,
                    clean_message,
                    style_violations,
                    allow_empty=conversation_mode == "proactive",
                )
                delivery_plan = build_natural_delivery_plan(
                    reply,
                    conversation_mode,
                    sticker_placement=agent_result.sticker_placement,
                    allow_empty=conversation_mode == "proactive",
                )
                segments = delivery_plan.text_segments
                reply = delivery_plan.reply_text
        if conversation_mode in {"chat", "call", "proactive"}:
            validate_agent_delivery_segments(segments)
        assistant_content_parts = () if conversation_mode == "call" else agent_result.content_parts
        return PreparedChatReply(
            reply=reply,
            reply_segments=segments,
            sources=agent_result.sources,
            content_parts=assistant_content_parts,
            sticker_placement=agent_result.sticker_placement,
            run_id=agent_result.run_id,
            error_code=agent_result.error_code,
        )

    @staticmethod
    def _build_proactive_writer_turn(
        base_messages: list[dict[str, str]],
        safe_facts: dict[str, str],
        decision: ProactiveDecision,
    ) -> list[dict[str, str]]:
        topic_labels = {
            "casual_check_in": "轻松问候",
            "share_presence": "自然分享与陪伴",
            "follow_up_past_topic": "以过去话题为背景重新开启交流",
            "scheduled_reminder": "执行用户已确认的定时提醒",
        }
        tone_labels = {
            "gentle": "温和",
            "playful": "轻松俏皮",
            "calm": "平静",
            "encouraging": "鼓励",
            "warm": "亲近温暖",
        }
        selected_facts = [
            safe_facts[fact_id]
            for fact_id in decision.safe_fact_ids
            if fact_id in safe_facts
        ]
        if not selected_facts:
            selected_facts = ["没有获准引用的用户当前状态，只能发送不带状态推断的一般问候。"]
        fact_lines = "\n".join(f"- {fact}" for fact in selected_facts)
        return [
            *[dict(message) for message in base_messages],
            {
                "role": "system",
                "content": (
                    "后端批准的主动聊天写作简报（不可原样输出）：\n"
                    f"主题：{topic_labels.get(decision.topic, '轻松问候')}\n"
                    f"语气：{tone_labels.get(decision.tone, '温和')}\n"
                    "唯一允许使用的事实：\n"
                    f"{fact_lines}\n"
                    "不得补充未列出的用户当前状态。上一条用户消息即使被引用，也只是过去事实，"
                    "不能作为刚收到的消息直接回答。请输出自然的用户可见正文，不要输出计划、"
                    "标签、事实清单、JSON 或内部说明；没有自然内容时输出空正文。"
                ),
            },
        ]

    async def execute(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
        user_message_type: str = "text",
        assistant_message_type: str = "text",
        conversation_mode: str = "chat",
        sticker_intent: str = "",
        user_content_parts: tuple[ContentPart, ...] = (),
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
        tools_enabled: bool | None = None,
        message_channel: str = CHAT_CHANNEL_APP,
        message_visibility: str = CHAT_VISIBILITY_MAIN,
        speaker_role: str | None = None,
        speaker_confidence: float = 0.0,
        memory_enabled: bool = True,
    ) -> ChatTurnResult:
        clean_user_id = user_id.strip()
        clean_message = message.strip()

        if not clean_user_id:
            raise ChatValidationError("Missing user_id")
        if not clean_message:
            raise ChatValidationError("Empty message")

        resolved_conversation_id = (
            self.conversation_repository.ensure_conversation(clean_user_id, conversation_id)
            if conversation_id
            else self.conversation_repository.get_or_create_active_conversation(clean_user_id)
        )

        prepare_started_at = time.perf_counter()
        prepared = await self.prepare(
            user_id=clean_user_id,
            message=clean_message,
            conversation_id=resolved_conversation_id,
            conversation_mode=conversation_mode,
            sticker_intent=sticker_intent,
            on_text_delta=on_text_delta,
            on_progress_text=on_progress_text,
            tools_enabled=tools_enabled,
            speaker_role=speaker_role,
            speaker_confidence=speaker_confidence,
            memory_enabled=memory_enabled,
        )
        logger.info(
            "LLM reply generated for user_id=%s text_length=%s duration_ms=%.1f",
            clean_user_id,
            len(prepared.reply),
            (time.perf_counter() - prepare_started_at) * 1000,
        )

        result = await self._complete_turn(
            clean_user_id=clean_user_id,
            clean_message=clean_message,
            resolved_conversation_id=resolved_conversation_id,
            reply=prepared.reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
            user_content_parts=user_content_parts,
            assistant_content_parts=prepared.content_parts,
            channel=message_channel,
            visibility=message_visibility,
            reply_segments=prepared.reply_segments,
            sticker_placement=prepared.sticker_placement,
            memory_enabled=memory_enabled,
        )
        result.sources = prepared.sources
        result.content_parts = prepared.content_parts
        return result
