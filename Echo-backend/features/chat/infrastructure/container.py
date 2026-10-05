from shared.config import settings

from features.chat.application.accept_message import AcceptChatMessage, ChatIntakePolicy
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
    ProactiveDecisionPlannerAdapter,
    RelationshipTurnRecorderAdapter,
    VoiceReplySynthesizerAdapter,
)
from features.chat.infrastructure.async_postgres_repository import (
    PostgresAsyncChatRepository,
)
from features.chat.infrastructure.events import get_chat_event_broker
from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)

_generate_chat_reply_use_case: GenerateChatReply | None = None
_send_chat_message_use_case: SendChatMessage | None = None
_clear_chat_context_use_case: ClearChatContext | None = None
_list_chat_messages_use_case: ListChatMessages | None = None
_accept_chat_message_use_case: AcceptChatMessage | None = None
_process_pending_chat_turns_use_case: ProcessPendingChatTurns | None = None
_delivery_timing_policy: DeliveryTimingPolicy | None = None


def get_delivery_timing_policy() -> DeliveryTimingPolicy:
    global _delivery_timing_policy
    if _delivery_timing_policy is None:
        _delivery_timing_policy = DeliveryTimingPolicy(
            followup_text_delay_ms=settings.chat_followup_text_delay_ms,
            final_text_delay_ms=settings.chat_final_text_delay_ms,
            sticker_delay_ms=settings.chat_sticker_delay_ms,
        )
    return _delivery_timing_policy


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
            proactive_planner=ProactiveDecisionPlannerAdapter(),
            schedule_repository=PostgresProactiveChatRepository(),
            summary_update_in_background=True,
            call_reply_max_chars=settings.call_reply_max_chars,
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
        _accept_chat_message_use_case = AcceptChatMessage(
            PostgresAsyncChatRepository(),
            ChatIntakePolicy(
                message_max_chars=settings.chat_message_max_chars,
                quiet_window_ms=settings.chat_batch_quiet_window_ms,
                maximum_window_ms=settings.chat_batch_max_window_ms,
                maximum_batch_messages=settings.chat_batch_max_messages,
                maximum_batch_characters=settings.chat_batch_max_chars,
                maximum_queued_messages=settings.chat_queue_max_messages,
            ),
        )
    return _accept_chat_message_use_case


def get_process_pending_chat_turns_use_case() -> ProcessPendingChatTurns:
    global _process_pending_chat_turns_use_case
    if _process_pending_chat_turns_use_case is None:
        _process_pending_chat_turns_use_case = ProcessPendingChatTurns(
            repository=PostgresAsyncChatRepository(),
            reply_generator=get_generate_chat_reply_use_case(),
            request_guard=InMemoryChatRequestGuard(),
            event_broker=get_chat_event_broker(),
            timing_policy=get_delivery_timing_policy(),
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
    global _delivery_timing_policy
    _generate_chat_reply_use_case = None
    _send_chat_message_use_case = None
    _clear_chat_context_use_case = None
    _list_chat_messages_use_case = None
    _accept_chat_message_use_case = None
    _process_pending_chat_turns_use_case = None
    _delivery_timing_policy = None
