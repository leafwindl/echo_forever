import threading

from features.agent.public import enrich_chat
from providers.llm_provider import get_llm_provider
from shared.config import settings

from features.chat.domain.entities import ChatContext, MemoryExtractionScheduleResult
from features.chat.domain.repositories import ChatContextRepository, ChatConversationRepository
from features.chat.domain.services import (
    ChatContextProvider,
    ChatAgentEnricher,
    ChatLLM,
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


class ChatAgentEnricherAdapter(ChatAgentEnricher):
    async def enrich(self, user_id: str, message: str):
        return await enrich_chat(user_id, message)


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
    ) -> tuple[int, int]:
        return postgres_repositories.add_chat_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            user_message_type=user_message_type,
            assistant_message_type=assistant_message_type,
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


class ChatContextProviderAdapter(ChatContextProvider):
    async def build_context(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
        conversation_mode: str,
    ) -> ChatContext:
        context = await build_chat_context(
            user_id,
            user_message,
            conversation_id=conversation_id,
            conversation_mode=conversation_mode,
        )
        return ChatContext(
            messages=context.messages,
            history_messages=context.history_messages,
            conversation_summary=context.conversation_summary,
            long_term_memories=context.long_term_memories,
            memory_retrieval_mode=context.memory_retrieval_mode,
            pause_followup_questions=context.pause_followup_questions,
        )


class ChatLLMAdapter(ChatLLM):
    async def generate_reply(self, messages: list[dict]) -> str:
        provider = get_llm_provider()
        return await provider.chat_completion(messages=messages)


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
