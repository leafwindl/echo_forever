from collections.abc import AsyncIterator
from typing import Protocol

from features.chat.domain.entities import ChatContext, MemoryExtractionScheduleResult


class ChatContextProvider(Protocol):
    async def build_context(
        self,
        user_id: str,
        user_message: str,
        conversation_id: str,
    ) -> ChatContext: ...


class ChatLLM(Protocol):
    async def generate_reply(self, messages: list[dict]) -> str: ...

    def stream_reply(self, messages: list[dict]) -> AsyncIterator[str]: ...


class ConversationSummaryUpdater(Protocol):
    async def maybe_update_summary(self, user_id: str, conversation_id: str) -> bool: ...


class MemoryExtractionScheduler(Protocol):
    def schedule(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: int,
    ) -> MemoryExtractionScheduleResult: ...


class ChatVoiceReplySynthesizer(Protocol):
    async def synthesize_reply(self, reply: str) -> tuple[str, ...]: ...

    async def start_streaming_segment(self, text: str) -> str: ...


class ChatRequestGuard(Protocol):
    def try_acquire(self, user_id: str) -> bool: ...

    def release(self, user_id: str) -> None: ...
