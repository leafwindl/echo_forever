import asyncio
import json
import logging
from typing import Optional

from features.memory.domain.entities import (
    MEMORY_EXTRACTION_JOB_TYPE,
    MemoryExtractionConfig,
    MemoryExtractionResult,
    MemoryGateResult,
)
from features.memory.domain.extraction_rules import (
    ALLOWED_MEMORY_TYPES,
    MIN_MEMORY_CONFIDENCE,
    build_extraction_messages,
    coerce_confidence,
    coerce_importance,
    find_duplicate_memory,
    parse_memory_extraction,
    should_extract_memory,
)
from features.memory.domain.repositories import (
    MemoryEmbeddingRepository,
    MemoryExtractionJobRepository,
    MemoryExtractionLLM,
    MemoryRepository,
)

logger = logging.getLogger(__name__)


class MemoryExtractionService:
    """Application service for scheduling and executing memory extraction jobs."""

    def __init__(
        self,
        memory_repository: MemoryRepository,
        embedding_repository: MemoryEmbeddingRepository,
        job_repository: MemoryExtractionJobRepository,
        llm: MemoryExtractionLLM,
        config: MemoryExtractionConfig,
    ):
        self.memory_repository = memory_repository
        self.embedding_repository = embedding_repository
        self.job_repository = job_repository
        self.llm = llm
        self.config = config
        self._background_tasks: set[asyncio.Task] = set()

    async def extract_and_store_memories(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: Optional[int] = None,
    ) -> MemoryExtractionResult:
        active_memories = self.memory_repository.list_active_memories(
            user_id,
            limit=self.config.max_existing_memories,
        )
        messages = build_extraction_messages(user_message, assistant_reply, active_memories)
        raw_result = await self.llm.request_memory_extraction(
            messages,
            model=self.config.model or None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        try:
            extracted_memories = parse_memory_extraction(raw_result)
        except json.JSONDecodeError:
            logger.warning("Memory extraction returned invalid JSON for user_id=%s: %s", user_id, raw_result)
            return MemoryExtractionResult(ignored=1)

        result = MemoryExtractionResult()
        for item in extracted_memories:
            await self._apply_extracted_memory(
                user_id=user_id,
                item=item,
                source_message_id=source_message_id,
                active_memories=active_memories,
                result=result,
            )

        logger.info(
            "Memory extraction finished for user_id=%s created=%s updated=%s deactivated=%s ignored=%s",
            user_id,
            result.created,
            result.updated,
            result.deactivated,
            result.ignored,
        )
        return result

    async def _apply_extracted_memory(
        self,
        user_id: str,
        item: dict,
        source_message_id: Optional[int],
        active_memories: list,
        result: MemoryExtractionResult,
    ):
        action = str(item.get("action", "ignore")).strip().lower()
        target_memory_id = str(item.get("target_memory_id") or item.get("memory_id") or "").strip()
        memory_type = str(item.get("memory_type", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        confidence = coerce_confidence(item.get("confidence"))
        importance = coerce_importance(item.get("importance"))

        if action in {"ignore", "none", ""}:
            result.ignored += 1
            return

        if action in {"deactivate", "delete", "forget", "remove"}:
            target_memory = self._resolve_target_memory(user_id, target_memory_id)
            if not target_memory and memory_type in ALLOWED_MEMORY_TYPES and content:
                target_memory = find_duplicate_memory(active_memories, memory_type, content)
            if target_memory and self.memory_repository.deactivate_memory(user_id, target_memory.memory_id):
                self._safe_delete_memory_embedding(user_id, target_memory.memory_id)
                active_memories[:] = [
                    memory for memory in active_memories if memory.memory_id != target_memory.memory_id
                ]
                result.deactivated += 1
            else:
                result.ignored += 1
            return

        if memory_type not in ALLOWED_MEMORY_TYPES or not content or confidence < MIN_MEMORY_CONFIDENCE:
            result.ignored += 1
            return

        target_memory = self._resolve_target_memory(user_id, target_memory_id)
        duplicate_memory = find_duplicate_memory(active_memories, memory_type, content)

        if action == "update" and target_memory:
            updated = self.memory_repository.update_memory(
                user_id=user_id,
                memory_id=target_memory.memory_id,
                memory_type=memory_type,
                content=content,
                source_message_id=source_message_id,
                confidence=confidence,
                importance=importance,
            )
            if updated:
                await self._safe_upsert_memory_embedding(user_id, target_memory.memory_id, content)
                result.updated += 1
            else:
                result.ignored += 1
            return

        if duplicate_memory:
            if self.memory_repository.touch_memory(
                user_id,
                duplicate_memory.memory_id,
                source_message_id=source_message_id,
            ):
                result.updated += 1
            else:
                result.ignored += 1
            return

        memory_id = self.memory_repository.add_memory(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=importance,
        )
        await self._safe_upsert_memory_embedding(user_id, memory_id, content)
        created_memory = self.memory_repository.get_memory(user_id, memory_id)
        if created_memory:
            active_memories.append(created_memory)
        result.created += 1

    def _resolve_target_memory(self, user_id: str, target_memory_id: str):
        if not target_memory_id:
            return None
        return self.memory_repository.get_memory(user_id, target_memory_id)

    async def _safe_upsert_memory_embedding(self, user_id: str, memory_id: str, content: str):
        try:
            await self.embedding_repository.upsert_memory_embedding(user_id, memory_id, content)
        except ValueError as exc:
            logger.warning("Memory embedding skipped for user_id=%s memory_id=%s: %s", user_id, memory_id, exc)
        except Exception:
            logger.exception("Memory embedding upsert failed for user_id=%s memory_id=%s", user_id, memory_id)

    def _safe_delete_memory_embedding(self, user_id: str, memory_id: str):
        try:
            self.embedding_repository.delete_memory_embedding(user_id, memory_id)
        except Exception:
            logger.exception("Memory embedding delete failed for user_id=%s memory_id=%s", user_id, memory_id)

    def schedule_memory_extraction(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        source_message_id: Optional[int] = None,
    ) -> MemoryGateResult:
        gate_result = should_extract_memory(user_message)
        if not gate_result.should_extract:
            logger.info("Memory extraction skipped for user_id=%s reason=%s", user_id, gate_result.reason)
            return gate_result

        job_id = self.job_repository.create_extraction_job(
            {
                "user_id": user_id,
                "user_message": user_message,
                "assistant_reply": assistant_reply,
                "source_message_id": source_message_id,
            }
        )
        scheduled = self._schedule_memory_extraction_job(job_id)
        logger.info(
            "Memory extraction %s for user_id=%s reason=%s job_id=%s",
            "scheduled" if scheduled else "queued",
            user_id,
            gate_result.reason,
            job_id,
        )
        return MemoryGateResult(True, gate_result.reason, job_id=job_id)

    async def _run_memory_extraction_job(self, job_id: str):
        if not self.job_repository.claim_job(job_id):
            logger.info("Memory extraction job skipped because it is not runnable: job_id=%s", job_id)
            return

        job = self.job_repository.get_job(job_id)
        if not job:
            logger.warning("Memory extraction job disappeared after claim: job_id=%s", job_id)
            return

        payload = job["payload"]
        user_id = str(payload.get("user_id", ""))
        try:
            result = await self.extract_and_store_memories(
                user_id=user_id,
                user_message=str(payload.get("user_message", "")),
                assistant_reply=str(payload.get("assistant_reply", "")),
                source_message_id=payload.get("source_message_id"),
            )
            self.job_repository.complete_job(job_id)
            logger.info(
                "Memory extraction job completed for user_id=%s job_id=%s created=%s updated=%s deactivated=%s ignored=%s",
                user_id,
                job_id,
                result.created,
                result.updated,
                result.deactivated,
                result.ignored,
            )
        except Exception as exc:
            self.job_repository.fail_job(job_id, str(exc))
            logger.exception("Memory extraction job failed for user_id=%s job_id=%s", user_id, job_id)

    def _schedule_memory_extraction_job(self, job_id: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.info("Memory extraction job queued without running loop: job_id=%s", job_id)
            return False

        task = loop.create_task(self._run_memory_extraction_job(job_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return True

    def resume_pending_memory_extraction_jobs(self, limit: Optional[int] = None) -> int:
        self.job_repository.reset_running_jobs()
        scheduled_count = 0
        safe_limit = limit or self.config.max_resumed_jobs
        for job in self.job_repository.list_runnable_jobs(limit=safe_limit):
            if self._schedule_memory_extraction_job(str(job["job_id"])):
                scheduled_count += 1
        return scheduled_count
