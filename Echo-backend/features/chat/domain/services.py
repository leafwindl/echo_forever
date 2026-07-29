from typing import Protocol

from features.agent.domain.entities import AgentEnrichment
from features.chat.domain.entities import ChatContext, MemoryExtractionScheduleResult


class ChatContextProvider(Protocol):
    async def build_context(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
        conversation_mode: str,
    ) -> ChatContext: ...


class ChatLLM(Protocol):
    async def generate_reply(self, messages: list[dict]) -> str: ...


class ChatAgentEnricher(Protocol):
    async def enrich(self, user_id: str, message: str) -> AgentEnrichment: ...


class ConversationSummaryUpdater(Protocol):
    async def maybe_update_summary(self, user_id: str, conversation_id: str) -> bool: ...


class MemoryExtractionScheduler(Protocol):
    def schedule(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: int,
        candidate_user_messages: tuple[tuple[int, str], ...],
        force_batch_review: bool,
    ) -> MemoryExtractionScheduleResult: ...


class RelationshipTurnRecorder(Protocol):
    def record(
        self,
        user_id: str,
        user_message: str,
        source_message_id: int,
    ) -> bool: ...


class ChatVoiceReplySynthesizer(Protocol):
    async def synthesize_reply(self, reply: str) -> tuple[str, ...]: ...


class ChatRequestGuard(Protocol):
    def try_acquire(self, user_id: str) -> bool: ...

    def release(self, user_id: str) -> None: ...
