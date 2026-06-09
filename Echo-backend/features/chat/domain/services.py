from typing import Protocol

from features.chat.domain.entities import ChatContext, MemoryExtractionScheduleResult


class ChatContextProvider(Protocol):
    async def build_context(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
    ) -> ChatContext:
        ...


class ChatLLM(Protocol):
    async def generate_reply(self, messages: list[dict]) -> str:
        ...


class ConversationSummaryUpdater(Protocol):
    async def maybe_update_summary(self, user_id: str, conversation_id: str) -> bool:
        ...


class MemoryExtractionScheduler(Protocol):
    def schedule(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: int,
    ) -> MemoryExtractionScheduleResult:
        ...
