from shared.config import settings

from features.chat.application.accept_message import AcceptChatMessage
from features.chat.application.clear_context import ClearChatContext
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.application.list_messages import ListChatMessages
from features.chat.application.process_turns import ProcessPendingChatTurns
from features.chat.application.send_message import SendChatMessage
from features.chat.domain.delivery_timing import DeliveryTimingPolicy
from features.chat.infrastructure.adapters import (
    ChatAgentOrchestratorAdapter,
    ChatContextProviderAdapter,
    ChatContextRepositoryAdapter,
    ChatConversationRepositoryAdapter,
    ChatHistoryRepositoryAdapter,
    ConversationSummaryUpdaterAdapter,
    InMemoryChatRequestGuard,
    MemoryExtractionSchedulerAdapter,
    PostgresChatRequestResultRepositoryAdapter,
    RelationshipTurnRecorderAdapter,
    VoiceReplySynthesizerAdapter,
)
from features.chat.infrastructure.async_postgres_repository import (
    PostgresAsyncChatRepository,
)
from features.chat.infrastructure.events import get_chat_event_broker

_generate_chat_reply_use_case: GenerateChatReply | None = None
_send_chat_message_use_case: SendChatMessage | None = None
_clear_chat_context_use_case: ClearChatContext | None = None
_list_chat_messages_use_case: ListChatMessages | None = None
_accept_chat_message_use_case: AcceptChatMessage | None = None
_process_pending_chat_turns_use_case: ProcessPendingChatTurns | None = None


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


def get_list_chat_messages_use_case() -> ListChatMessages:
    global _list_chat_messages_use_case
    if _list_chat_messages_use_case is None:
        _list_chat_messages_use_case = ListChatMessages(ChatHistoryRepositoryAdapter())
    return _list_chat_messages_use_case


def get_accept_chat_message_use_case() -> AcceptChatMessage:
    global _accept_chat_message_use_case
    if _accept_chat_message_use_case is None:
        _accept_chat_message_use_case = AcceptChatMessage(PostgresAsyncChatRepository())
    return _accept_chat_message_use_case


def get_process_pending_chat_turns_use_case() -> ProcessPendingChatTurns:
    global _process_pending_chat_turns_use_case
    if _process_pending_chat_turns_use_case is None:
        _process_pending_chat_turns_use_case = ProcessPendingChatTurns(
            repository=PostgresAsyncChatRepository(),
            reply_generator=get_generate_chat_reply_use_case(),
            request_guard=InMemoryChatRequestGuard(),
            event_broker=get_chat_event_broker(),
            timing_policy=DeliveryTimingPolicy(),
            lease_seconds=settings.chat_turn_lease_seconds,
        )
    return _process_pending_chat_turns_use_case


def get_async_chat_repository() -> PostgresAsyncChatRepository:
    return PostgresAsyncChatRepository()


def reset_generate_chat_reply_use_case_for_tests():
    global _generate_chat_reply_use_case, _send_chat_message_use_case
    global _clear_chat_context_use_case
    global _list_chat_messages_use_case
    global _accept_chat_message_use_case, _process_pending_chat_turns_use_case
    _generate_chat_reply_use_case = None
    _send_chat_message_use_case = None
    _clear_chat_context_use_case = None
    _list_chat_messages_use_case = None
    _accept_chat_message_use_case = None
    _process_pending_chat_turns_use_case = None
