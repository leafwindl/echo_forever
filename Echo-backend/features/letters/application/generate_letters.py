from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from features.agent.domain.entities import AgentRunStatus
from features.agent.public import run_daily_letter_agent
from features.letters.application.assemble_context import LetterContext, LetterContextAssembler
from features.letters.application.generate_image import GenerateLetterImage
from features.letters.domain.entities import LetterAgentOutput, LetterGenerationTask
from features.letters.domain.output import LetterOutputValidationError, parse_letter_agent_output
from features.letters.domain.repositories import LetterRepository

logger = logging.getLogger(__name__)

LetterAgentRunner = Callable[[str, str, list[dict]], Awaitable[object]]
Clock = Callable[[], datetime]

FORMAT_REPAIR_INSTRUCTION = (
    "上一份来信没有通过结构化输出校验。不要重新构思内容，不要调用工具；只修复 JSON 格式、"
    "缺失字段和字段类型。保留有证据的正文与观点，最终只输出一个符合 daily_letter 契约的 JSON。"
)


@dataclass(frozen=True)
class LetterGenerationPolicy:
    minimum_chars: int
    maximum_chars: int
    batch_size: int
    context_version: str


class GenerateDueLetters:
    def __init__(
        self,
        repository: LetterRepository,
        context_assembler: LetterContextAssembler,
        image_generator: GenerateLetterImage,
        policy: LetterGenerationPolicy,
        agent_runner: LetterAgentRunner = run_daily_letter_agent,
        clock: Clock | None = None,
    ):
        self.repository = repository
        self.context_assembler = context_assembler
        self.image_generator = image_generator
        self.policy = policy
        self.agent_runner = agent_runner
        self.clock = clock or _utc_now

    async def execute(self, now_utc: datetime | None = None) -> int:
        now = _as_utc(now_utc or self.clock())
        self.repository.ensure_due_generation_tasks(now)
        processed = 0
        while processed < self.policy.batch_size:
            task = self.repository.claim_generation_task(now)
            if task is None:
                break
            await self._process_task(task)
            processed += 1
            now = _as_utc(self.clock())
        return processed

    async def _process_task(self, task: LetterGenerationTask) -> None:
        try:
            context = await self.context_assembler.build(
                user_id=task.user_id,
                local_date=task.local_date,
                timezone_name=task.timezone,
            )
            if not context.has_user_interaction:
                self.repository.create_skipped(task, "no_interaction")
                logger.info(
                    "Daily letter skipped letter_id=%s reason=no_interaction",
                    task.letter_id,
                )
                return

            output, agent_run_id = await self._generate_output(task, context)
            source_ids = _ground_source_ids(output, context)
            source_memory_ids = _ground_memory_ids(output, context.source_memory_ids)
            image_result = await self.image_generator.execute(
                user_id=task.user_id,
                local_date=task.local_date.isoformat(),
                letter_id=task.letter_id,
                image_brief=output.image_brief,
                deadline=task.publish_at,
            )
            persisted = self.repository.complete_generation(
                task,
                subject=output.subject,
                content=output.content,
                reflection=output.reflection,
                mood=output.mood,
                image_brief=output.image_brief,
                source_message_ids=source_ids,
                source_memory_ids=source_memory_ids,
                agent_run_id=agent_run_id,
                context_version=self.policy.context_version,
                context_snapshot=context.snapshot,
                image_storage_key=image_result.storage_key,
                image_content_type=image_result.content_type,
                image_width=image_result.width,
                image_height=image_result.height,
                image_byte_size=image_result.byte_size or None,
                image_provider=image_result.provider,
                image_model=image_result.model,
                image_reference_version=image_result.reference_version,
                image_status=image_result.status,
                image_failure_code=image_result.failure_code,
            )
            if not persisted:
                raise RuntimeError("letter_generation_claim_lost")
            logger.info(
                "Daily letter generated letter_id=%s messages=%s memories=%s image=%s",
                task.letter_id,
                context.raw_message_count,
                context.memory_count,
                image_result.status,
            )
        except Exception as exc:
            self.repository.fail_generation(task, type(exc).__name__, _as_utc(self.clock()))
            logger.warning(
                "Daily letter generation failed letter_id=%s",
                task.letter_id,
                exc_info=True,
            )

    async def _generate_output(
        self,
        task: LetterGenerationTask,
        context: LetterContext,
    ) -> tuple[LetterAgentOutput, str]:
        objective = (
            f"Generate Echo daily letter letter_id={task.letter_id} "
            f"local_date={task.local_date.isoformat()}"
        )
        result = await self.agent_runner(task.user_id, objective, context.messages)
        raw_output = _successful_reply(result)
        try:
            return self._parse_output(raw_output), str(getattr(result, "run_id", ""))
        except LetterOutputValidationError:
            logger.info("Daily letter JSON repair requested letter_id=%s", task.letter_id)

        repair_messages = [
            *context.messages,
            {"role": "assistant", "content": raw_output[:8000]},
            {"role": "system", "content": FORMAT_REPAIR_INSTRUCTION},
        ]
        repaired = await self.agent_runner(
            task.user_id,
            f"Repair Echo daily letter JSON letter_id={task.letter_id}",
            repair_messages,
        )
        return self._parse_output(_successful_reply(repaired)), str(
            getattr(repaired, "run_id", "") or getattr(result, "run_id", "")
        )

    def _parse_output(self, raw_output: str) -> LetterAgentOutput:
        return parse_letter_agent_output(
            raw_output,
            minimum_chars=self.policy.minimum_chars,
            maximum_chars=self.policy.maximum_chars,
        )


def _successful_reply(result: object) -> str:
    if getattr(result, "status", None) == AgentRunStatus.FAILED:
        raise RuntimeError(str(getattr(result, "error_code", "agent_failed")))
    reply = str(getattr(result, "reply_text", "")).strip()
    if not reply:
        raise RuntimeError("daily_letter_agent_empty_reply")
    return reply


def _ground_source_ids(output: LetterAgentOutput, context: LetterContext) -> list[int]:
    allowed = set(context.source_message_ids)
    grounded = [message_id for message_id in output.source_message_ids if message_id in allowed]
    if not any(message_id in context.user_message_ids for message_id in grounded):
        grounded.extend(context.user_message_ids[:1])
    return list(dict.fromkeys(grounded))


def _ground_memory_ids(output: LetterAgentOutput, available: tuple[str, ...]) -> list[str]:
    allowed = set(available)
    return list(
        dict.fromkeys(memory_id for memory_id in output.source_memory_ids if memory_id in allowed)
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
