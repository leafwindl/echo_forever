from typing import Optional

from shared.config import settings

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.send_message import SendChatMessage
from features.chat.infrastructure.adapters import (
    ChatContextProviderAdapter,
    ChatConversationRepositoryAdapter,
    ChatLLMAdapter,
    ConversationSummaryUpdaterAdapter,
    InMemoryChatRequestGuard,
    MemoryExtractionSchedulerAdapter,
    VoiceReplySynthesizerAdapter,
)

_generate_chat_reply_use_case: Optional[GenerateChatReply] = None
_send_chat_message_use_case: Optional[SendChatMessage] = None


def get_generate_chat_reply_use_case() -> GenerateChatReply:
    global _generate_chat_reply_use_case
    if _generate_chat_reply_use_case is None:
        _generate_chat_reply_use_case = GenerateChatReply(
            conversation_repository=ChatConversationRepositoryAdapter(),
            context_provider=ChatContextProviderAdapter(),
            llm=ChatLLMAdapter(),
            summary_updater=ConversationSummaryUpdaterAdapter(),
            memory_scheduler=MemoryExtractionSchedulerAdapter(),
            summary_update_in_background=True,
        )
    return _generate_chat_reply_use_case


def get_send_chat_message_use_case() -> SendChatMessage:
    global _send_chat_message_use_case
    if _send_chat_message_use_case is None:
        _send_chat_message_use_case = SendChatMessage(
            chat_reply_generator=get_generate_chat_reply_use_case(),
            voice_reply_synthesizer=VoiceReplySynthesizerAdapter(),
            request_guard=InMemoryChatRequestGuard(),
            streaming_voice_segment_max_chars=min(settings.tts_segment_max_chars, 24),
            voice_reply_max_chars=settings.tts_reply_max_chars,
        )
    return _send_chat_message_use_case


def reset_generate_chat_reply_use_case_for_tests():
    global _generate_chat_reply_use_case, _send_chat_message_use_case
    _generate_chat_reply_use_case = None
    _send_chat_message_use_case = None
