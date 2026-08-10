import asyncio
import json
import struct
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.entities import AgentRunStatus, AgentTurnResult
from features.letters.application.assemble_context import LetterContext
from features.letters.application.generate_image import (
    GenerateLetterImage,
    LetterImagePolicy,
    LetterImageResult,
)
from features.letters.application.generate_letters import (
    GenerateDueLetters,
    LetterGenerationPolicy,
)
from features.letters.domain.entities import LetterGenerationTask
from features.letters.domain.output import (
    LetterOutputValidationError,
    parse_letter_agent_output,
)
from features.letters.infrastructure import postgres_repository as repository_module
from features.letters.infrastructure.postgres_repository import (
    LetterRepositoryConfig,
    PostgresLetterRepository,
)
from providers.minimax_image_provider import (
    MiniMaxImageGenerationProvider,
    MiniMaxImageProviderConfig,
)


def _letter_json(**overrides) -> str:
    payload = {
        "subject": "今天想留给你的话",
        "content": "昨天我们谈到工作节奏，我注意到你一边想推进事情，一边也在担心自己太累。",
        "mood": "quiet_encouragement",
        "core_topics": ["工作节奏", "休息边界"],
        "reflection": "我觉得真正稳定的前进，不是每次都把自己推到极限。",
        "closing_style": "statement",
        "image_brief": {
            "emotion": "安静关心",
            "scene": "清晨窗边的 Echo 整理桌上的纸张",
            "visual_symbols": ["晨光", "合上的笔记本"],
            "avoid": ["文字", "真实用户形象"],
        },
        "source_message_ids": [2, 999],
        "source_memory_ids": ["memory-a", "invented-memory"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _task(*, attempt_count: int = 1) -> LetterGenerationTask:
    scheduled_at = datetime(2026, 8, 9, 7, 45, tzinfo=UTC)
    return LetterGenerationTask(
        letter_id="letter-a",
        user_id="user-a",
        local_date=date(2026, 8, 8),
        timezone="UTC",
        scheduled_at=scheduled_at,
        publish_at=scheduled_at + timedelta(minutes=15),
        attempt_count=attempt_count,
        max_attempts=3,
    )


def _context(*, has_user_interaction: bool = True) -> LetterContext:
    return LetterContext(
        messages=[{"role": "system", "content": "daily letter evidence"}],
        source_message_ids=(1, 2),
        user_message_ids=(1,) if has_user_interaction else (),
        source_memory_ids=("memory-a",),
        raw_message_count=2,
        memory_count=1,
        has_user_interaction=has_user_interaction,
        snapshot={"message_count": 2, "session_count": 1},
    )


class _FakeLetterRepository:
    def __init__(self, tasks):
        self.tasks = list(tasks)
        self.completed = []
        self.failed = []
        self.skipped = []
        self.ensure_calls = []

    def ensure_due_generation_tasks(self, now_utc):
        self.ensure_calls.append(now_utc)
        return len(self.tasks)

    def claim_generation_task(self, _now_utc):
        return self.tasks.pop(0) if self.tasks else None

    def complete_generation(self, task, **values):
        self.completed.append((task, values))
        return True

    def create_skipped(self, task, reason):
        self.skipped.append((task, reason))
        return True

    def fail_generation(self, task, error_code, now_utc):
        self.failed.append((task, error_code, now_utc))


class _FakeContextAssembler:
    def __init__(self, context):
        self.context = context

    async def build(self, **_kwargs):
        return self.context


class _FakeImageGenerator:
    def __init__(self, result=None):
        self.result = result or LetterImageResult(status="disabled")
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class LetterGenerationTests(unittest.IsolatedAsyncioTestCase):
    def test_image_brief_normalizes_string_lists_from_model_output(self):
        raw_output = _letter_json(
            image_brief={
                "emotion": "安静关心",
                "scene": "清晨窗边的 Echo 整理桌上的纸张",
                "visual_symbols": "晨光、合上的笔记本",
                "avoid": "文字，真实用户形象",
            }
        )

        output = parse_letter_agent_output(
            raw_output,
            minimum_chars=10,
            maximum_chars=1000,
        )

        self.assertEqual(output.image_brief["visual_symbols"], ["晨光", "合上的笔记本"])
        self.assertEqual(output.image_brief["avoid"], ["文字", "真实用户形象"])

    async def test_invalid_json_gets_one_format_repair_and_grounded_sources(self):
        repository = _FakeLetterRepository([_task()])
        image_generator = _FakeImageGenerator(
            LetterImageResult(status="failed", failure_code="provider_timeout")
        )
        replies = ["not-json", _letter_json()]
        agent_calls = []

        async def run_agent(user_id, objective, messages):
            agent_calls.append((user_id, objective, messages))
            return AgentTurnResult(
                status=AgentRunStatus.COMPLETED,
                reply_text=replies.pop(0),
                run_id=f"run-{len(agent_calls)}",
            )

        worker = GenerateDueLetters(
            repository,
            _FakeContextAssembler(_context()),
            image_generator,
            LetterGenerationPolicy(10, 1000, 10, "context-v2"),
            agent_runner=run_agent,
            clock=lambda: datetime(2026, 8, 9, 7, 50, tzinfo=UTC),
        )

        processed = await worker.execute(datetime(2026, 8, 9, 7, 45, tzinfo=UTC))

        self.assertEqual(processed, 1)
        self.assertEqual(len(agent_calls), 2)
        self.assertIn("Repair Echo daily letter JSON", agent_calls[1][1])
        self.assertEqual(repository.failed, [])
        values = repository.completed[0][1]
        self.assertEqual(values["source_message_ids"], [2, 1])
        self.assertEqual(values["source_memory_ids"], ["memory-a"])
        self.assertEqual(values["agent_run_id"], "run-2")
        self.assertEqual(values["image_status"], "failed")
        self.assertEqual(values["image_failure_code"], "provider_timeout")
        self.assertEqual(image_generator.calls[0]["deadline"], _task().publish_at)

    async def test_no_interaction_is_skipped_without_agent_or_image(self):
        repository = _FakeLetterRepository([_task()])
        image_generator = _FakeImageGenerator()
        agent_called = False

        async def run_agent(*_args):
            nonlocal agent_called
            agent_called = True
            return AgentTurnResult(reply_text=_letter_json())

        worker = GenerateDueLetters(
            repository,
            _FakeContextAssembler(_context(has_user_interaction=False)),
            image_generator,
            LetterGenerationPolicy(10, 1000, 10, "context-v2"),
            agent_runner=run_agent,
        )

        self.assertEqual(await worker.execute(_task().scheduled_at), 1)
        self.assertFalse(agent_called)
        self.assertEqual(image_generator.calls, [])
        self.assertEqual(repository.skipped[0][1], "no_interaction")

    async def test_agent_failure_enters_repository_retry_flow(self):
        repository = _FakeLetterRepository([_task()])

        async def run_agent(*_args):
            return AgentTurnResult(
                status=AgentRunStatus.FAILED,
                error_code="llm_timeout",
            )

        worker = GenerateDueLetters(
            repository,
            _FakeContextAssembler(_context()),
            _FakeImageGenerator(),
            LetterGenerationPolicy(10, 1000, 10, "context-v2"),
            agent_runner=run_agent,
            clock=lambda: datetime(2026, 8, 9, 7, 46, tzinfo=UTC),
        )

        self.assertEqual(await worker.execute(_task().scheduled_at), 1)
        self.assertEqual(repository.completed, [])
        self.assertEqual(repository.failed[0][1], "RuntimeError")


class LetterOutputTests(unittest.TestCase):
    def test_reflection_is_required(self):
        with self.assertRaises(LetterOutputValidationError):
            parse_letter_agent_output(
                _letter_json(reflection=""),
                minimum_chars=10,
                maximum_chars=1000,
            )

    def test_image_brief_redacts_direct_contact_details(self):
        output = parse_letter_agent_output(
            _letter_json(
                image_brief={
                    "emotion": "开心",
                    "scene": "给 13800138000 和 test@example.com 画一张图",
                    "visual_symbols": ["https://private.example/path"],
                    "avoid": ["文字"],
                }
            ),
            minimum_chars=10,
            maximum_chars=1000,
        )

        brief_text = json.dumps(output.image_brief, ensure_ascii=False)
        self.assertNotIn("13800138000", brief_text)
        self.assertNotIn("test@example.com", brief_text)
        self.assertNotIn("https://private.example/path", brief_text)

    def test_daily_letter_agent_policy_has_no_chat_sticker_instructions(self):
        messages = OrchestrateChatWithAgent._build_initial_messages(
            messages=[],
            conversation_mode="daily_letter",
            sticker_intent="",
            allow_proactive_stickers=True,
            proactive_sticker_due=True,
        )

        instruction = messages[0]["content"]
        self.assertIn("当前无可用工具", instruction)
        self.assertIn("不得搜索、选择或发送聊天表情包", instruction)
        self.assertNotIn("send_sticker 返回 completed", instruction)


class _FakeImageProvider:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return self.content, "image/png"


class _FakeImageStorage:
    def __init__(self):
        self.calls = []

    def put_bytes(self, relative_key, content, content_type, **kwargs):
        self.calls.append((relative_key, content, content_type, kwargs))
        return f"echo/{relative_key}"

    def download_url(self, relative_key, **_kwargs):
        return f"https://cos.example/{relative_key}"


class LetterImageTests(unittest.IsolatedAsyncioTestCase):
    def _policy(self):
        return LetterImagePolicy(
            enabled=True,
            aspect_ratio="4:3",
            maximum_attempts=2,
            maximum_bytes=1024,
            timeout_seconds=10,
            provider_name="minimax",
            model="image-01",
            reference_version="echo-v1.jpg",
            reference_storage_key="assets/echo-reference/echo-v1.jpg",
        )

    async def test_valid_image_is_uploaded_with_dimensions(self):
        png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + struct.pack(">II", 640, 480)
        provider = _FakeImageProvider(png)
        storage = _FakeImageStorage()
        now = datetime(2026, 8, 9, 7, 50, tzinfo=UTC)
        generator = GenerateLetterImage(provider, storage, self._policy(), clock=lambda: now)

        result = await generator.execute(
            user_id="user-a",
            local_date="2026-08-08",
            letter_id="letter-a",
            image_brief={"emotion": "calm", "scene": "window"},
            deadline=now + timedelta(minutes=10),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual((result.width, result.height), (640, 480))
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(storage.calls), 1)

    async def test_publish_deadline_prevents_provider_call(self):
        provider = _FakeImageProvider(b"unused")
        now = datetime(2026, 8, 9, 8, 0, tzinfo=UTC)
        generator = GenerateLetterImage(
            provider,
            _FakeImageStorage(),
            self._policy(),
            clock=lambda: now,
        )

        result = await generator.execute(
            user_id="user-a",
            local_date="2026-08-08",
            letter_id="letter-a",
            image_brief={"emotion": "calm", "scene": "window"},
            deadline=now,
        )

        self.assertEqual(result.failure_code, "publish_deadline_exceeded")
        self.assertEqual(provider.calls, 0)


class _FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class LetterRepositoryTests(unittest.TestCase):
    def _repository(self):
        return PostgresLetterRepository(
            LetterRepositoryConfig(
                default_timezone="Asia/Shanghai",
                default_publish_time="08:00",
                generation_time="07:45",
                generation_version="letter-agent-v2",
                maximum_attempts=3,
                lease_seconds=480,
                retry_offsets_seconds=(300, 720),
            )
        )

    def test_first_failure_retries_at_configured_absolute_offset(self):
        cursor = _FakeCursor()
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            now = datetime(2026, 8, 9, 7, 46, tzinfo=UTC)
            self._repository().fail_generation(_task(attempt_count=1), "llm_timeout", now)
        finally:
            repository_module.transaction = original_transaction

        params = cursor.calls[0][1]
        self.assertEqual(params[0], "retry_wait")
        self.assertTrue(params[1])
        self.assertEqual(params[2], datetime(2026, 8, 9, 7, 50, tzinfo=UTC))

    def test_publish_only_updates_letters_without_notification_outbox(self):
        cursor = _FakeCursor()
        original_transaction = repository_module.transaction
        repository_module.transaction = lambda: _FakeTransaction(_FakeConnection(cursor))
        try:
            published = self._repository().publish_due(
                datetime(2026, 8, 9, 8, 0, tzinfo=UTC)
            )
        finally:
            repository_module.transaction = original_transaction

        self.assertEqual(published, 1)
        self.assertIn("UPDATE daily_letters", cursor.calls[0][0])
        self.assertNotIn("notification_outbox", cursor.calls[0][0])


class MiniMaxImageProviderTests(unittest.TestCase):
    def test_request_uses_official_subject_reference_contract(self):
        provider = MiniMaxImageGenerationProvider(
            MiniMaxImageProviderConfig(
                api_key="secret",
                base_url="https://api.minimaxi.com/v1/image_generation",
                model="image-01",
                timeout_seconds=30,
            )
        )

        payload = provider._request_payload(
            "Echo by the window",
            ("https://cos.example/echo-v1.jpg",),
            "4:3",
        )

        self.assertEqual(payload["response_format"], "url")
        self.assertFalse(payload["prompt_optimizer"])
        self.assertEqual(
            payload["subject_reference"],
            [
                {
                    "type": "character",
                    "image_file": "https://cos.example/echo-v1.jpg",
                }
            ],
        )

    def test_response_parser_accepts_data_image_urls(self):
        class _Response:
            def json(self):
                return {"data": {"image_urls": ["https://images.example/echo.png"]}}

        class _ImageResponse:
            content = b"image-bytes"
            headers = {"content-type": "image/png"}

            def raise_for_status(self):
                return None

        class _Client:
            async def get(self, _url):
                return _ImageResponse()

        async def parse():
            return await MiniMaxImageGenerationProvider._parse_response(_Response(), _Client())

        image, content_type = asyncio.run(parse())

        self.assertEqual(image, b"image-bytes")
        self.assertEqual(content_type, "image/png")


if __name__ == "__main__":
    unittest.main()
