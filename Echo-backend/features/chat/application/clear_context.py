from features.chat.domain.entities import ChatContextClearResult, ChatValidationError
from features.chat.domain.repositories import ChatContextRepository


class ClearChatContext:
    def __init__(self, context_repository: ChatContextRepository):
        self.context_repository = context_repository

    def execute(self, user_id: str) -> ChatContextClearResult:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ChatValidationError("Missing user_id")

        deleted_messages, reset_conversations = self.context_repository.clear_context(
            clean_user_id
        )
        return ChatContextClearResult(
            deleted_messages=deleted_messages,
            reset_conversations=reset_conversations,
        )
