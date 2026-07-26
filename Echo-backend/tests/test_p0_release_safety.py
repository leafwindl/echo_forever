import io
import json
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.datastructures import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.admin.interface.router import verify_admin_debug_access
from features.chat.interface.router import chat_clear
from features.chat.interface.schemas import ChatRequest
from features.system.interface.router import readiness_check
from features.voice.interface.router import read_upload_with_limit
from shared.config import settings
from shared.interface.dependencies import CurrentUser
from shared.security.logging_filter import SensitiveDataFilter


class AdminDebugSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_enabled = settings.enable_admin_debug_api
        self.original_token = settings.admin_debug_token

    def tearDown(self):
        settings.enable_admin_debug_api = self.original_enabled
        settings.admin_debug_token = self.original_token

    def test_disabled_admin_api_returns_not_found(self):
        settings.enable_admin_debug_api = False

        with self.assertRaises(HTTPException) as error:
            verify_admin_debug_access("anything")

        self.assertEqual(error.exception.status_code, 404)

    def test_placeholder_admin_token_cannot_enable_api(self):
        settings.enable_admin_debug_api = True
        settings.admin_debug_token = "change-me"

        with self.assertRaises(HTTPException) as error:
            verify_admin_debug_access("change-me")

        self.assertEqual(error.exception.status_code, 503)

    def test_strong_admin_token_is_compared(self):
        settings.enable_admin_debug_api = True
        settings.admin_debug_token = "a" * 32

        with self.assertRaises(HTTPException) as error:
            verify_admin_debug_access("wrong")
        self.assertEqual(error.exception.status_code, 403)

        self.assertIsNone(verify_admin_debug_access("a" * 32))


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

    @patch("features.chat.interface.router.clear_user_chat_context")
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
