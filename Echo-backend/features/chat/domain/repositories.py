from typing import Protocol

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    ChatHistoryMessage,
    ChatReplyDeliveryResult,
    ChatRequestClaim,
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
        limit: int,
    ) -> tuple[tuple[ChatHistoryMessage, ...], bool]: ...


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
