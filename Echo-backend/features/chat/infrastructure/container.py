from features.chat.application.clear_context import ClearChatContext
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.send_message import SendChatMessage
from features.chat.infrastructure.adapters import (
    ChatAgentOrchestratorAdapter,
    ChatContextProviderAdapter,
    ChatContextRepositoryAdapter,
    ChatConversationRepositoryAdapter,
    ConversationSummaryUpdaterAdapter,
    InMemoryChatRequestGuard,
    MemoryExtractionSchedulerAdapter,
    PostgresChatRequestResultRepositoryAdapter,
    RelationshipTurnRecorderAdapter,
    VoiceReplySynthesizerAdapter,
)

_generate_chat_reply_use_case: GenerateChatReply | None = None
_send_chat_message_use_case: SendChatMessage | None = None
_clear_chat_context_use_case: ClearChatContext | None = None


def get_generate_chat_reply_use_case() -> GenerateChatReply:
    global _generate_chat_reply_use_case
    if _generate_chat_reply_use_case is None:
        _generate_chat_reply_use_case = GenerateChatReply(
            conversation_repository=ChatConversationRepositoryAdapter(),
            context_provider=ChatContextProviderAdapter(),
            summary_updater=ConversationSummaryUpdaterAdapter(),
            memory_scheduler=MemoryExtractionSchedulerAdapter(),
            relationship_recorder=RelationshipTurnRecorderAdapter(),
            agent_orchestrator=ChatAgentOrchestratorAdapter(),
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
            request_result_repository=PostgresChatRequestResultRepositoryAdapter(),
        )
    return _send_chat_message_use_case


def get_clear_chat_context_use_case() -> ClearChatContext:
    global _clear_chat_context_use_case
    if _clear_chat_context_use_case is None:
        _clear_chat_context_use_case = ClearChatContext(
            context_repository=ChatContextRepositoryAdapter()
        )
    return _clear_chat_context_use_case


def reset_generate_chat_reply_use_case_for_tests():
    global _generate_chat_reply_use_case, _send_chat_message_use_case
    global _clear_chat_context_use_case
    _generate_chat_reply_use_case = None
    _send_chat_message_use_case = None
    _clear_chat_context_use_case = None
