from typing import Protocol

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    CHAT_CHANNEL_APP,
    CHAT_VISIBILITY_MAIN,
    ChatBatchInput,
    ChatDeliveryPresentation,
    ChatHistoryMessage,
    ChatMessageAcceptance,
    ChatReplyDeliveryResult,
    ChatReplyGroup,
    ChatRequestClaim,
    ChatTurnJob,
    PreparedChatReply,
)


class ChatConversationRepository(Protocol):
    def ensure_conversation(self, user_id: str, conversation_id: str | None) -> str: ...

    def get_or_create_active_conversation(self, user_id: str) -> str: ...

    def add_chat_turn(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_message_type: str,
        assistant_message_type: str,
        user_content_parts: tuple[ContentPart, ...] = (),
        assistant_content_parts: tuple[ContentPart, ...] = (),
        channel: str = CHAT_CHANNEL_APP,
        visibility: str = CHAT_VISIBILITY_MAIN,
    ) -> tuple[int, int]: ...

    def count_user_messages(self, user_id: str, conversation_id: str) -> int: ...

    def list_recent_user_messages(
        self,
        user_id: str,
        conversation_id: str,
        limit: int,
    ) -> tuple[tuple[int, str], ...]: ...


class ChatContextRepository(Protocol):
    def clear_context(self, user_id: str) -> tuple[int, int]: ...


class ChatHistoryRepository(Protocol):
    def get_or_create_active_conversation(self, user_id: str) -> str: ...

    def list_messages_page(
        self,
        user_id: str,
        conversation_id: str,
        before_id: int | None,
        after_id: int | None,
        limit: int,
    ) -> tuple[tuple[ChatHistoryMessage, ...], bool]: ...


class ChatIntakeRepository(Protocol):
    def accept_message(
        self,
        *,
        user_id: str,
        client_message_id: str,
        message_type: str,
        content: str,
        content_parts: tuple[ContentPart, ...],
        quiet_window_ms: int,
        maximum_window_ms: int,
        maximum_batch_messages: int,
        maximum_batch_characters: int,
        maximum_queued_messages: int,
    ) -> ChatMessageAcceptance: ...


class ChatTurnRepository(Protocol):
    def claim_due_turn(self, lease_seconds: int) -> ChatTurnJob | None: ...

    def load_batch(self, turn: ChatTurnJob) -> ChatBatchInput: ...

    def complete_turn(
        self,
        turn: ChatTurnJob,
        reply: PreparedChatReply,
        presentation: ChatDeliveryPresentation,
    ) -> ChatReplyGroup | None: ...

    def fail_turn(self, turn_id: str, error_code: str) -> bool: ...

    def reschedule_turn(self, turn_id: str, delay_ms: int) -> bool: ...

    def has_running_turn(self, user_id: str, conversation_id: str) -> bool: ...


class ChatRequestResultRepository(Protocol):
    def claim(
        self,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> ChatRequestClaim: ...

    def complete(
        self,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        result: ChatReplyDeliveryResult,
    ) -> None: ...

    def abandon(self, user_id: str, request_id: str, request_fingerprint: str) -> None: ...
