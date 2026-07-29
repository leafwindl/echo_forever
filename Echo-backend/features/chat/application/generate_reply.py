import asyncio
import logging
import time

from features.chat.domain.dialogue_style import (
    NATURAL_DIALOGUE_RETRY_INSTRUCTION,
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.domain.entities import ChatTurnResult, ChatValidationError
from features.chat.domain.repositories import ChatConversationRepository
from features.chat.domain.services import (
    ChatContextProvider,
    ChatLLM,
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
        llm: ChatLLM,
        summary_updater: ConversationSummaryUpdater,
        memory_scheduler: MemoryExtractionScheduler,
        relationship_recorder: RelationshipTurnRecorder | None = None,
        summary_update_in_background: bool = False,
    ):
        self.conversation_repository = conversation_repository
        self.context_provider = context_provider
        self.llm = llm
        self.summary_updater = summary_updater
        self.memory_scheduler = memory_scheduler
        self.relationship_recorder = relationship_recorder
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
    ) -> ChatTurnResult:
        user_message_id, assistant_message_id = self.conversation_repository.add_chat_turn(
            user_id=clean_user_id,
            conversation_id=resolved_conversation_id,
            user_message=clean_message,
            assistant_reply=reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
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
            source_message_id=user_message_id,
            candidate_user_messages=candidate_user_messages,
            force_batch_review=(user_message_count % 5 == 0),
        )

        if self.relationship_recorder is not None:
            relationship_recorded = self.relationship_recorder.record(
                user_id=clean_user_id,
                user_message=clean_message,
                source_message_id=user_message_id,
            )
            if not relationship_recorded:
                logger.warning("Relationship turn recording skipped for user_id=%s", clean_user_id)

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
        )

    async def execute(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
        user_message_type: str = "text",
        assistant_message_type: str = "text",
        conversation_mode: str = "chat",
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

        context_started_at = time.perf_counter()
        context = await self.context_provider.build_context(
            clean_user_id,
            clean_message,
            resolved_conversation_id,
            conversation_mode,
        )
        logger.info(
            "Chat context completed duration_ms=%.1f",
            (time.perf_counter() - context_started_at) * 1000,
        )
        llm_started_at = time.perf_counter()
        reply = await self.llm.generate_reply(context.messages)
        style_violations = find_dialogue_style_violations(
            reply,
            clean_message,
            pause_followup_questions=context.pause_followup_questions,
        )
        if style_violations:
            logger.warning(
                "Dialogue style retry requested violation_types=%s",
                ",".join(style_violations),
            )
            try:
                reply = await self.llm.generate_reply(
                    [
                        *context.messages,
                        {"role": "system", "content": NATURAL_DIALOGUE_RETRY_INSTRUCTION},
                    ]
                )
            except Exception:
                logger.warning("Dialogue style retry failed", exc_info=True)

            remaining_violations = find_dialogue_style_violations(
                reply,
                clean_message,
                pause_followup_questions=context.pause_followup_questions,
            )
            if remaining_violations:
                logger.warning(
                    "Dialogue style fallback applied violation_types=%s",
                    ",".join(remaining_violations),
                )
                reply = apply_dialogue_fallback(
                    reply,
                    clean_message,
                    remaining_violations,
                )
        logger.info(
            "LLM reply generated for user_id=%s text_length=%s duration_ms=%.1f",
            clean_user_id,
            len(reply),
            (time.perf_counter() - llm_started_at) * 1000,
        )

        return await self._complete_turn(
            clean_user_id=clean_user_id,
            clean_message=clean_message,
            resolved_conversation_id=resolved_conversation_id,
            reply=reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
        )
