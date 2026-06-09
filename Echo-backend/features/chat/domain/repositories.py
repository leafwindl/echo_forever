from typing import Optional, Protocol


class ChatConversationRepository(Protocol):
    def ensure_conversation(self, user_id: str, conversation_id: Optional[str]) -> str:
        ...

    def get_or_create_active_conversation(self, user_id: str) -> str:
        ...

    def add_chat_turn(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_message_type: str,
        assistant_message_type: str,
    ) -> tuple[int, int]:
        ...
