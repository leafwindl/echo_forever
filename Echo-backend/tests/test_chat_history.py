import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from features.agent.domain.entities import ContentPart
from features.chat.application.list_messages import ListChatMessages
from features.chat.domain.entities import ChatHistoryMessage, ChatHistoryPage, ChatValidationError
from features.chat.interface.router import chat_messages
from shared.interface.dependencies import CurrentUser


class FakeChatHistoryRepository:
    def __init__(self, items=(), has_more=False):
        self.items = tuple(items)
        self.has_more = has_more
        self.calls = []

    def get_or_create_active_conversation(self, user_id):
        self.calls.append(("conversation", user_id))
        return "conv_active"

    def list_messages_page(self, user_id, conversation_id, before_id, after_id, limit):
        self.calls.append(("page", user_id, conversation_id, before_id, after_id, limit))
        return self.items, self.has_more


def message(message_id: int, *, role: str = "user") -> ChatHistoryMessage:
    return ChatHistoryMessage(
        message_id=message_id,
        role=role,
        message_type="text",
        content=f"message-{message_id}",
        content_parts=(),
        created_at=datetime(2026, 8, 6, 8, message_id, tzinfo=UTC),
    )


class ListChatMessagesTests(unittest.TestCase):
    def test_lists_latest_page_and_returns_oldest_id_as_cursor(self):
        repository = FakeChatHistoryRepository(
            items=(message(11), message(12, role="assistant")),
            has_more=True,
        )

        result = ListChatMessages(repository).execute(" user-a ", limit=10)

        self.assertEqual(result.conversation_id, "conv_active")
        self.assertEqual([item.message_id for item in result.items], [11, 12])
        self.assertTrue(result.has_more)
        self.assertEqual(result.next_before_id, 11)
        self.assertEqual(
            repository.calls[-1],
            ("page", "user-a", "conv_active", None, None, 10),
        )

    def test_last_page_has_no_next_cursor(self):
        result = ListChatMessages(
            FakeChatHistoryRepository(items=(message(1),), has_more=False)
        ).execute("user-a", before_id=10, limit=10)

        self.assertFalse(result.has_more)
        self.assertIsNone(result.next_before_id)

    def test_rejects_invalid_cursor_and_limit(self):
        use_case = ListChatMessages(FakeChatHistoryRepository())
        with self.assertRaises(ChatValidationError):
            use_case.execute("user-a", before_id=0)
        with self.assertRaises(ChatValidationError):
            use_case.execute("user-a", limit=51)


class ChatHistoryInterfaceTests(unittest.TestCase):
    @patch("features.chat.interface.router.list_chat_messages")
    def test_maps_sticker_attachment_without_exposing_internal_prompt(self, list_messages):
        list_messages.return_value = ChatHistoryPage(
            conversation_id="conv_active",
            items=(
                ChatHistoryMessage(
                    message_id=20,
                    role="user",
                    message_type="sticker",
                    content="",
                    content_parts=(
                        ContentPart(
                            type="sticker",
                            sticker_id="stk_wave",
                            url="https://example.test/wave.png",
                        ),
                    ),
                    created_at=datetime(2026, 8, 6, 8, 0, tzinfo=UTC),
                ),
            ),
            has_more=False,
            next_before_id=None,
        )

        response = chat_messages(
            CurrentUser(user_id="user-a"),
            before_id=None,
            after_id=None,
            limit=10,
        )

        list_messages.assert_called_once_with(
            "user-a",
            before_id=None,
            after_id=None,
            limit=10,
        )
        self.assertEqual(response.items[0].content, "")
        self.assertEqual(response.items[0].content_parts[0].sticker_id, "stk_wave")


if __name__ == "__main__":
    unittest.main()
