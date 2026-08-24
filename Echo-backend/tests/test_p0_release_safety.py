import io
import json
import logging
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import (
    ChatAcceptedTurn,
    ChatHistoryMessage,
    ChatMessageAcceptance,
    ChatTurnStatus,
)
from features.chat.interface.router import accept_message, chat_clear
from features.chat.interface.schemas import AsyncChatMessageRequest
from features.stickers.domain.entities import Sticker
from features.system.interface.router import readiness_check
from features.voice.interface.router import read_upload_with_limit
from shared.interface.dependencies import CurrentUser
from shared.security.logging_filter import SensitiveDataFilter


class RequestSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_upload_is_read_within_limit(self):
        upload = UploadFile(filename="voice.mp3", file=io.BytesIO(b"12345"))

        result = await read_upload_with_limit(upload, max_bytes=5)

        self.assertEqual(result, b"12345")

    async def test_voice_upload_over_limit_returns_413(self):
        upload = UploadFile(filename="voice.mp3", file=io.BytesIO(b"123456"))

        with self.assertRaises(HTTPException) as error:
            await read_upload_with_limit(upload, max_bytes=5)

        self.assertEqual(error.exception.status_code, 413)

    async def test_async_sticker_message_uses_server_metadata(self):
        sticker = Sticker(
            sticker_id="stk_wave",
            owner_type="user",
            source="uploaded",
            url="https://example.test/wave.png",
            content_type="image/png",
            description="开心挥手",
            semantic_tags=("开心", "挥手"),
            status="active",
            created_at=datetime.now(UTC),
        )
        request = AsyncChatMessageRequest(
            client_message_id="00000000-0000-4000-8000-000000000001",
            message_type="sticker",
            sticker_id="stk_wave",
        )
        with (
            patch("features.chat.interface.router.consume_chat_quota"),
            patch(
                "features.chat.interface.router.sticker_repository.get",
                return_value=sticker,
            ),
            patch(
                "features.chat.interface.router.accept_chat_message",
                return_value=ChatMessageAcceptance(
                    conversation_id="conv-active",
                    message=ChatHistoryMessage(
                        message_id=1,
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
                        created_at=datetime.now(UTC),
                    ),
                    turn=ChatAcceptedTurn(
                        turn_id="turn-1",
                        status=ChatTurnStatus.COLLECTING,
                    ),
                ),
            ) as accept,
        ):
            result = accept_message(
                request,
                CurrentUser(user_id="user-a"),
            )

        self.assertEqual(result.message.message_type, "sticker")
        accept.assert_called_once()
        call = accept.call_args.kwargs
        self.assertEqual(call["message_type"], "sticker")
        self.assertEqual(call["content_parts"][0].sticker_id, "stk_wave")

    @patch("features.chat.interface.router.get_chat_event_broker")
    @patch("features.chat.interface.router.list_chat_messages")
    @patch("features.chat.interface.router.clear_chat_context")
    async def test_user_can_clear_only_authenticated_chat_context(
        self,
        clear_context,
        list_messages,
        get_broker,
    ):
        clear_context.return_value.deleted_messages = 7
        clear_context.return_value.reset_conversations = 1
        list_messages.return_value.conversation_id = "conv-reset"
        get_broker.return_value.publish = AsyncMock()

        result = await chat_clear(CurrentUser(user_id="user-a"))

        clear_context.assert_called_once_with("user-a")
        get_broker.return_value.publish.assert_awaited_once()
        self.assertEqual(result.deleted_messages, 7)
        self.assertEqual(result.reset_conversations, 1)


class ReadinessTests(unittest.TestCase):
    @patch("features.system.interface.router.is_database_ready", return_value=True)
    def test_ready_database_returns_success(self, _):
        self.assertEqual(readiness_check(), {"status": "ready", "database": "ok"})

    @patch("features.system.interface.router.is_database_ready", return_value=False)
    def test_unavailable_database_returns_503_without_exception_details(self, _):
        response = readiness_check()
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(body, {"status": "not_ready", "database": "unavailable"})


class LoggingSafetyTests(unittest.TestCase):
    def test_sensitive_query_values_in_url_objects_are_redacted(self):
        class URLValue:
            def __str__(self):
                return "https://example.test/login?secret=private&js_code=temporary"

        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="HTTP Request: %s",
            args=(URLValue(),),
            exc_info=None,
        )

        SensitiveDataFilter().filter(record)

        self.assertNotIn("private", record.getMessage())
        self.assertNotIn("temporary", record.getMessage())
        self.assertEqual(record.getMessage().count("[REDACTED]"), 2)


if __name__ == "__main__":
    unittest.main()
