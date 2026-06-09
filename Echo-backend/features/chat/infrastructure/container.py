from typing import Optional

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.infrastructure.adapters import (
    ChatContextProviderAdapter,
    ChatConversationRepositoryAdapter,
    ChatLLMAdapter,
    ConversationSummaryUpdaterAdapter,
    MemoryExtractionSchedulerAdapter,
)

_generate_chat_reply_use_case: Optional[GenerateChatReply] = None


def get_generate_chat_reply_use_case() -> GenerateChatReply:
    global _generate_chat_reply_use_case
    if _generate_chat_reply_use_case is None:
        _generate_chat_reply_use_case = GenerateChatReply(
            conversation_repository=ChatConversationRepositoryAdapter(),
            context_provider=ChatContextProviderAdapter(),
            llm=ChatLLMAdapter(),
            summary_updater=ConversationSummaryUpdaterAdapter(),
            memory_scheduler=MemoryExtractionSchedulerAdapter(),
        )
    return _generate_chat_reply_use_case


def reset_generate_chat_reply_use_case_for_tests():
    global _generate_chat_reply_use_case
    _generate_chat_reply_use_case = None
