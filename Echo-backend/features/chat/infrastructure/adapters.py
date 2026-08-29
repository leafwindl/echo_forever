import threading
from collections.abc import Awaitable, Callable

from shared.config import settings

from features.agent.domain.entities import ContentPart, SourceReference
from features.agent.domain.services import ProactiveDecisionPlanner
from features.agent.public import plan_proactive_message, run_chat_agent
from features.chat.domain.entities import (
    CHAT_CHANNEL_APP,
    CHAT_VISIBILITY_MAIN,
    ChatContext,
    ChatHistoryMessage,
    ChatReplyDeliveryResult,
    ChatRequestClaim,
    ChatRequestClaimStatus,
    MemoryExtractionScheduleResult,
)
from features.chat.domain.repositories import (
    ChatContextRepository,
    ChatConversationRepository,
    ChatHistoryRepository,
    ChatRequestResultRepository,
)
from features.chat.domain.services import (
    ChatAgentOrchestrator,
    ChatContextProvider,
    ChatRequestGuard,
    ChatVoiceReplySynthesizer,
    ConversationSummaryUpdater,
    MemoryExtractionScheduler,
    RelationshipTurnRecorder,
)
from features.chat.infrastructure import postgres_repositories
from features.chat.infrastructure.context_builder import build_chat_context
from features.chat.infrastructure.conversation_summary import maybe_update_conversation_summary
from features.memory.public import schedule_memory_extraction
from features.persona.public import get_persona
from features.relationship.public import record_relationship_turn


class ChatAgentOrchestratorAdapter(ChatAgentOrchestrator):
    async def run(
        self,
        user_id: str,
        message: str,
        messages: list[dict],
        conversation_id: str | None = None,
        conversation_mode: str = "chat",
        sticker_intent: str = "",
        allow_proactive_stickers: bool = True,
        proactive_sticker_due: bool = False,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
        tools_enabled: bool | None = None,
    ):
        return await run_chat_agent(
            user_id,
            message,
            messages,
            conversation_id=conversation_id,
            conversation_mode=conversation_mode,
            sticker_intent=sticker_intent,
            allow_proactive_stickers=allow_proactive_stickers,
            proactive_sticker_due=proactive_sticker_due,
            on_text_delta=on_text_delta,
            on_progress_text=on_progress_text,
            tools_enabled=tools_enabled,
        )


class ProactiveDecisionPlannerAdapter(ProactiveDecisionPlanner):
    async def decide(
        self,
        planner_facts: dict[str, object],
        *,
        force_send: bool = False,
    ):
        return await plan_proactive_message(
            planner_facts,
            force_send=force_send,
        )


class InMemoryChatRequestGuard(ChatRequestGuard):
    _lock = threading.Lock()
    _active_user_ids: set[str] = set()

    def try_acquire(self, user_id: str) -> bool:
        if not settings.enable_chat_request_serialization:
            return True

        clean_user_id = user_id.strip()
        if not clean_user_id:
            return True

        with self._lock:
            if clean_user_id in self._active_user_ids:
                return False
            self._active_user_ids.add(clean_user_id)
            return True

    def release(self, user_id: str) -> None:
        if not settings.enable_chat_request_serialization:
            return

        clean_user_id = user_id.strip()
        if not clean_user_id:
            return

        with self._lock:
            self._active_user_ids.discard(clean_user_id)


class ChatConversationRepositoryAdapter(ChatConversationRepository):
    def ensure_conversation(self, user_id: str, conversation_id: str | None) -> str:
        return postgres_repositories.ensure_conversation(user_id, conversation_id)

    def get_or_create_active_conversation(self, user_id: str) -> str:
        return postgres_repositories.get_or_create_active_conversation(user_id)

    def add_chat_turn(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_message_type: str,
        assistant_message_type: str,
        user_content_parts=(),
        assistant_content_parts=(),
        channel: str = CHAT_CHANNEL_APP,
        visibility: str = CHAT_VISIBILITY_MAIN,
    ) -> tuple[int, int]:
        return postgres_repositories.add_chat_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
            user_content_parts=user_content_parts,
            assistant_content_parts=assistant_content_parts,
            channel=channel,
            visibility=visibility,
        )

    def count_user_messages(self, user_id: str, conversation_id: str) -> int:
        return postgres_repositories.count_user_messages(user_id, conversation_id)

    def list_recent_user_messages(
        self,
        user_id: str,
        conversation_id: str,
        limit: int,
    ) -> tuple[tuple[int, str], ...]:
        return postgres_repositories.list_recent_user_messages(user_id, conversation_id, limit)


class ChatContextRepositoryAdapter(ChatContextRepository):
    def clear_context(self, user_id: str) -> tuple[int, int]:
        return postgres_repositories.clear_context(user_id)


class ChatHistoryRepositoryAdapter(ChatHistoryRepository):
    def get_or_create_active_conversation(self, user_id: str) -> str:
        return postgres_repositories.get_or_create_active_conversation(user_id)

    def list_messages_page(
        self,
        user_id: str,
        conversation_id: str,
        before_id: int | None,
        after_id: int | None,
        limit: int,
    ) -> tuple[tuple[ChatHistoryMessage, ...], bool]:
        rows, has_more = postgres_repositories.list_messages_page(
            user_id,
            conversation_id,
            before_id,
            after_id,
            limit,
        )
        return (
            tuple(ChatHistoryMessage(**row) for row in rows),
            has_more,
        )


class PostgresChatRequestResultRepositoryAdapter(ChatRequestResultRepository):
    def claim(
        self,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> ChatRequestClaim:
        status, payload = postgres_repositories.claim_chat_request(
            user_id,
            request_id,
            request_fingerprint,
        )
        result = self._result_from_payload(payload) if payload is not None else None
        return ChatRequestClaim(status=ChatRequestClaimStatus(status), result=result)

    def complete(
        self,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        result: ChatReplyDeliveryResult,
    ) -> None:
        postgres_repositories.complete_chat_request(
            user_id,
            request_id,
            request_fingerprint,
            {
                "reply": result.reply,
                "audio_urls": list(result.audio_urls),
                "user_message_id": result.user_message_id,
                "assistant_message_id": result.assistant_message_id,
                "conversation_id": result.conversation_id,
                "sources": [vars(source) for source in result.sources],
                "content_parts": [vars(part) for part in result.content_parts],
            },
        )

    def abandon(self, user_id: str, request_id: str, request_fingerprint: str) -> None:
        postgres_repositories.abandon_chat_request(
            user_id,
            request_id,
            request_fingerprint,
        )

    @staticmethod
    def _result_from_payload(payload: dict[str, object]) -> ChatReplyDeliveryResult:
        return ChatReplyDeliveryResult(
            reply=str(payload.get("reply") or ""),
            audio_urls=tuple(str(url) for url in payload.get("audio_urls") or []),
            sources=tuple(
                SourceReference(**item)
                for item in payload.get("sources") or []
                if isinstance(item, dict)
            ),
            content_parts=tuple(
                ContentPart(**item)
                for item in payload.get("content_parts") or []
                if isinstance(item, dict)
            ),
            user_message_id=(
                int(payload["user_message_id"])
                if payload.get("user_message_id") is not None
                else None
            ),
            assistant_message_id=(
                int(payload["assistant_message_id"])
                if payload.get("assistant_message_id") is not None
                else None
            ),
            conversation_id=str(payload.get("conversation_id") or ""),
        )


class ChatContextProviderAdapter(ChatContextProvider):
    async def build_context(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
        conversation_mode: str,
        history_before_message_id: int | None = None,
        speaker_role: str | None = None,
        memory_enabled: bool = True,
    ) -> ChatContext:
        context = await build_chat_context(
            user_id,
            user_message,
            conversation_id=conversation_id,
            conversation_mode=conversation_mode,
            history_before_message_id=history_before_message_id,
            speaker_role=speaker_role,
            memory_enabled=memory_enabled,
        )
        return ChatContext(
            messages=context.messages,
            history_messages=context.history_messages,
            conversation_summary=context.conversation_summary,
            long_term_memories=context.long_term_memories,
            memory_retrieval_mode=context.memory_retrieval_mode,
            pause_followup_questions=context.pause_followup_questions,
            suppress_repeated_greeting=context.suppress_repeated_greeting,
            allow_proactive_stickers=context.allow_proactive_stickers,
            proactive_sticker_due=context.proactive_sticker_due,
            temporal_context=context.temporal_context,
            proactive_writer_messages=context.proactive_writer_messages,
            proactive_safe_facts=context.proactive_safe_facts,
            proactive_planner_input=context.proactive_planner_input,
        )


class ConversationSummaryUpdaterAdapter(ConversationSummaryUpdater):
    async def maybe_update_summary(self, user_id: str, conversation_id: str) -> bool:
        return await maybe_update_conversation_summary(user_id, conversation_id)


class MemoryExtractionSchedulerAdapter(MemoryExtractionScheduler):
    def schedule(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: int,
        candidate_user_messages: tuple[tuple[int, str], ...],
        force_batch_review: bool,
    ) -> MemoryExtractionScheduleResult:
        result = schedule_memory_extraction(
            user_id=user_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            source_message_id=source_message_id,
            candidate_user_messages=candidate_user_messages,
            force_batch_review=force_batch_review,
        )
        return MemoryExtractionScheduleResult(
            should_extract=result.should_extract,
            reason=result.reason,
            job_id=result.job_id,
        )


class RelationshipTurnRecorderAdapter(RelationshipTurnRecorder):
    def record(
        self,
        user_id: str,
        user_message: str,
        source_message_id: int,
    ) -> bool:
        try:
            preferences = get_persona(user_id)
            record_relationship_turn(
                user_id=user_id,
                user_message=user_message,
                source_message_id=source_message_id,
                relationship_pace=(
                    preferences.relationship_pace if preferences.enabled else "natural"
                ),
            )
            return True
        except Exception:
            return False


class VoiceReplySynthesizerAdapter(ChatVoiceReplySynthesizer):
    async def synthesize_reply(self, reply: str) -> tuple[str, ...]:
        from features.voice.public import synthesize_voice_reply

        result = await synthesize_voice_reply(reply)
        return result.audio_urls
