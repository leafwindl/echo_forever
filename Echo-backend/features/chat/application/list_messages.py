from features.chat.domain.entities import ChatHistoryPage, ChatValidationError
from features.chat.domain.repositories import ChatHistoryRepository


class ListChatMessages:
    def __init__(self, repository: ChatHistoryRepository):
        self.repository = repository

    def execute(
        self,
        user_id: str,
        before_id: int | None = None,
        after_id: int | None = None,
        limit: int = 10,
    ) -> ChatHistoryPage:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ChatValidationError("user_id is required")
        if before_id is not None and before_id <= 0:
            raise ChatValidationError("before_id must be positive")
        if after_id is not None and after_id < 0:
            raise ChatValidationError("after_id must not be negative")
        if before_id is not None and after_id is not None:
            raise ChatValidationError("before_id and after_id cannot be combined")
        if not 1 <= limit <= 50:
            raise ChatValidationError("limit must be between 1 and 50")

        conversation_id = self.repository.get_or_create_active_conversation(clean_user_id)
        items, has_more = self.repository.list_messages_page(
            clean_user_id,
            conversation_id,
            before_id,
            after_id,
            limit,
        )
        return ChatHistoryPage(
            conversation_id=conversation_id,
            items=items,
            has_more=has_more,
            next_before_id=items[0].message_id if has_more and items else None,
            next_after_id=(
                items[-1].message_id
                if has_more and items and after_id is not None
                else None
            ),
        )
