import logging
from typing import Optional

from features.chat.domain.entities import ChatTurnResult, ChatValidationError
from features.chat.domain.repositories import ChatConversationRepository
from features.chat.domain.services import (
    ChatContextProvider,
    ChatLLM,
    ConversationSummaryUpdater,
    MemoryExtractionScheduler,
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
    ):
        self.conversation_repository = conversation_repository
        self.context_provider = context_provider
        self.llm = llm
        self.summary_updater = summary_updater
        self.memory_scheduler = memory_scheduler

    async def execute(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        user_message_type: str = "text",
        assistant_message_type: str = "text",
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

        context = await self.context_provider.build_context(
            clean_user_id,
            clean_message,
            resolved_conversation_id,
        )
        reply = await self.llm.generate_reply(context.messages)
        logger.info("LLM reply generated for user_id=%s", clean_user_id)

        user_message_id, assistant_message_id = self.conversation_repository.add_chat_turn(
            user_id=clean_user_id,
            conversation_id=resolved_conversation_id,
            user_message=clean_message,
            assistant_reply=reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
        )

        summary_updated = False
        try:
            summary_updated = await self.summary_updater.maybe_update_summary(
                clean_user_id,
                resolved_conversation_id,
            )
        except Exception:
            logger.exception(
                "Conversation summary update failed for conversation_id=%s",
                resolved_conversation_id,
            )

        memory_gate = self.memory_scheduler.schedule(
            user_id=clean_user_id,
            user_message=clean_message,
            assistant_reply=reply,
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
        )
