import asyncio
import logging
import time

from features.agent.domain.entities import ContentPart
from features.chat.domain.dialogue_style import (
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.domain.entities import (
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
        summary_update_in_background: bool = False,
    ):
        self.conversation_repository = conversation_repository
        self.context_provider = context_provider
        self.summary_updater = summary_updater
        self.memory_scheduler = memory_scheduler
        self.relationship_recorder = relationship_recorder
        self.agent_orchestrator = agent_orchestrator
        self.summary_update_in_background = summary_update_in_background
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
        reply_segments: tuple[str, ...] = (),
        sticker_placement: str = "after_text",
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
        )

        summary_updated, memory_gate = await self._run_post_persistence(
            clean_user_id=clean_user_id,
            clean_message=clean_message,
            resolved_conversation_id=resolved_conversation_id,
            reply=reply,
            source_message_id=user_message_id,
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
    ) -> tuple[bool, MemoryExtractionScheduleResult]:
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
    ) -> None:
        await self._run_post_persistence(
            clean_user_id=user_id,
            clean_message=user_message,
            resolved_conversation_id=conversation_id,
            reply=assistant_reply,
            source_message_id=source_message_id,
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
    ) -> PreparedChatReply:
        clean_user_id = user_id.strip()
        clean_message = message.strip()
        if not clean_user_id:
            raise ChatValidationError("Missing user_id")
        if not clean_message:
            raise ChatValidationError("Empty message")

        context_started_at = time.perf_counter()
        if history_before_message_id is None:
            context = await self.context_provider.build_context(
                clean_user_id,
                clean_message,
                conversation_id,
                conversation_mode,
            )
        else:
            context = await self.context_provider.build_context(
                clean_user_id,
                clean_message,
                conversation_id,
                conversation_mode,
                history_before_message_id=history_before_message_id,
            )
        if self.agent_orchestrator is None:
            raise RuntimeError("Unified Agent runtime is not configured")
        agent_result = await self.agent_orchestrator.run(
            clean_user_id,
            clean_message,
            context.messages,
            conversation_mode=conversation_mode,
            sticker_intent=sticker_intent,
            allow_proactive_stickers=context.allow_proactive_stickers,
        )
        logger.info(
            "Chat reply prepared duration_ms=%.1f",
            (time.perf_counter() - context_started_at) * 1000,
        )
        segments = tuple(
            segment.strip()
            for segment in agent_result.reply_segments
            if segment.strip()
        )
        if not segments and agent_result.reply_text.strip():
            segments = (agent_result.reply_text.strip(),)
        reply = "\n".join(segments)
        style_violations = find_dialogue_style_violations(
            reply,
            clean_message,
            pause_followup_questions=context.pause_followup_questions,
        )
        if style_violations:
            logger.warning(
                "Dialogue style fallback applied violation_types=%s",
                ",".join(style_violations),
            )
            reply = apply_dialogue_fallback(reply, clean_message, style_violations)
            segments = (reply,) if reply else ()
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
            reply_segments=prepared.reply_segments,
            sticker_placement=prepared.sticker_placement,
        )
        result.sources = prepared.sources
        result.content_parts = prepared.content_parts
        return result
