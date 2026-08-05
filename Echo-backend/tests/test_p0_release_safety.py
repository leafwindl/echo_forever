import io
import json
import logging
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.chat.domain.entities import ChatReplyDeliveryResult
from features.chat.interface.router import chat_clear, chat_send
from features.chat.interface.schemas import ChatRequest
from features.stickers.domain.entities import Sticker
from features.system.interface.router import readiness_check
from features.voice.interface.router import read_upload_with_limit
from shared.config import settings
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

    def test_chat_message_uses_configured_length_limit(self):
        original_limit = settings.chat_message_max_chars
        settings.chat_message_max_chars = 5
        try:
            with self.assertRaises(ValidationError):
                ChatRequest(user_id="user-a", message="123456")
            with self.assertRaises(ValidationError):
                ChatRequest(user_id="user-a", message="   ")
        finally:
            settings.chat_message_max_chars = original_limit

    def test_chat_request_accepts_one_sticker_without_text(self):
        request = ChatRequest(
            message="",
            content_parts=[{"type": "sticker", "sticker_id": "stk_wave"}],
        )

        self.assertEqual(request.content_parts[0].sticker_id, "stk_wave")
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="",
                mode="call",
                content_parts=[{"type": "sticker", "sticker_id": "stk_wave"}],
            )

    async def test_sticker_chat_uses_server_metadata_and_still_generates_reply(self):
        sticker = Sticker(
            sticker_id="stk_wave",
            owner_type="user",
            source="uploaded",
            url="https://example.test/wave.png",
            content_type="image/png",
            description="开心挥手",
            semantic_tags=("开心", "挥手"),
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        request = ChatRequest(
            message="",
            content_parts=[{"type": "sticker", "sticker_id": "stk_wave"}],
        )
        with (
            patch("features.chat.interface.router.consume_chat_quota"),
            patch(
                "features.chat.interface.router.sticker_repository.get",
                return_value=sticker,
            ),
            patch(
                "features.chat.interface.router.send_chat_message",
                new_callable=AsyncMock,
                return_value=ChatReplyDeliveryResult(reply="收到啦"),
            ) as send_message,
        ):
            http_request = Request(
                {
                    "type": "http",
                    "headers": [(b"x-request-id", b"request-test")],
                }
            )
            result = await chat_send(
                request,
                http_request,
                CurrentUser(user_id="user-a"),
            )

        self.assertEqual(result.reply, "收到啦")
        send_message.assert_awaited_once()
        call = send_message.await_args.kwargs
        self.assertEqual(call["user_message_type"], "sticker")
        self.assertEqual(call["sticker_intent"], "开心挥手 开心 挥手")
        self.assertIn("描述：开心挥手", call["message"])
        self.assertEqual(call["request_id"], "request-test")

    @patch("features.chat.interface.router.clear_chat_context")
    async def test_user_can_clear_only_authenticated_chat_context(self, clear_context):
        clear_context.return_value.deleted_messages = 7
        clear_context.return_value.reset_conversations = 1

        result = await chat_clear(CurrentUser(user_id="user-a"))

        clear_context.assert_called_once_with("user-a")
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
