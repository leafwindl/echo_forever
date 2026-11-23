"""模型↔工具循环与交付检查点。

这是一次 Agent turn 的内核：调用模型、执行工具、收集交付、按策略重试或兜底。
它不负责 run 记录的开始/结束（由 runtime 负责），也不负责构建初始消息或选择
工具范围（由 policy 负责）。

`run()` 返回一个不可变的 `LoopOutcome`，由 runtime 翻译成 `AgentTurnResult` 并
记录轨迹。这样"循环做了什么"和"这次 turn 记成什么"分成两件事。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from features.agent.application.call_progress import build_call_progress_text
from features.agent.application.delivery_gate import (
    STICKER_CLAIM_RETRY_INSTRUCTION,
    DeliveryGate,
)
from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.turn_fallbacks import TurnFallbacks
from features.agent.domain.delivery import (
    AgentDeliveryPlanError,
    build_natural_delivery_plan,
    prefix_codepoints,
    validate_agent_delivery_segments,
)
from features.agent.domain.entities import (
    AgentModelResponse,
    AgentToolCall,
    AgentToolResult,
    AgentToolStatus,
    ContentPart,
    SourceReference,
)
from features.agent.domain.repositories import AgentRunRepository
from features.agent.domain.services import (
    AgentConversationModel,
    AgentModelTimeoutError,
)
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.domain.turn_policy import TurnPolicy, TurnProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoopOutcome:
    """循环结束时的完整交付状态；completed 由 runtime 翻译成 run 状态。"""

    completed: bool = True
    text: str = ""
    segments: tuple[str, ...] = ()
    content_parts: tuple[ContentPart, ...] = ()
    sources: tuple[SourceReference, ...] = ()
    tool_results: tuple[AgentToolResult, ...] = ()
    sticker_placement: str = "after_text"
    model_steps: int = 0
    tool_calls: int = 0
    error_code: str | None = None


class ModelToolLoop:
    def __init__(
        self,
        *,
        model: AgentConversationModel,
        registry: ToolRegistry,
        executor: ToolExecutor,
        gate: DeliveryGate,
        fallbacks: TurnFallbacks,
        repository: AgentRunRepository,
        policy: TurnPolicy,
    ):
        self.model = model
        self.registry = registry
        self.executor = executor
        self.gate = gate
        self.fallbacks = fallbacks
        self.repository = repository
        self.policy = policy

    async def run(
        self,
        *,
        user_id: str,
        message: str,
        conversation_id: str | None,
        conversation_mode: str,
        profile: TurnProfile,
        messages: list[dict],
        run_id: str,
        deadline: float,
        tools_enabled: bool,
        allowed_tool_names: tuple[str, ...] | None,
        require_tool: bool = False,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> LoopOutcome:
        agent_messages = [dict(item) for item in messages]
        tool_results: list[AgentToolResult] = []
        content_parts: list[ContentPart] = []
        sources: list[SourceReference] = []
        sticker_placement = "after_text"
        emitted_beats: tuple[str, ...] = ()
        model_steps = 0
        tool_call_count = 0
        progress_reported = False
        llm_timeout_retries_remaining = profile.retries.llm_timeout
        delivery_format_retries_remaining = profile.retries.delivery_format
        sticker_claim_retries_remaining = profile.retries.sticker_claim
        tools = (
            self.registry.model_descriptions(conversation_mode, allowed_tool_names)
            if tools_enabled
            else ()
        )
        maximum_tool_calls = profile.max_tool_calls
        final_error: str | None = None
        try:
            while model_steps < profile.max_steps:
                model_steps += 1
                tool_choice = (
                    "required" if require_tool and not tool_results else "auto"
                )
                step_tool_names = {
                    str(item.get("function", {}).get("name") or "") for item in tools
                }
                response, llm_timeout_retries_remaining = await self._complete_model(
                    messages=agent_messages,
                    tools=tools,
                    structured_output=profile.structured_output,
                    tool_choice=tool_choice,
                    deadline=deadline,
                    run_id=run_id,
                    timeout_retries_remaining=llm_timeout_retries_remaining,
                    on_text_delta=on_text_delta,
                )
                if require_tool and not tool_results and not response.tool_calls:
                    logger.warning(
                        "Agent required tool call was not returned; falling back to auto "
                        "run_id=%s",
                        run_id,
                    )
                    require_tool = False

                finish_reason = response.finish_reason.strip().lower()
                if finish_reason == "length" and (
                    conversation_mode == "daily_letter" or not response.text.strip()
                ):
                    if (
                        conversation_mode == "chat"
                        and delivery_format_retries_remaining > 0
                    ):
                        delivery_format_retries_remaining -= 1
                        agent_messages = self.gate.delivery_retry_messages(
                            agent_messages,
                        )
                        tools = ()
                        logger.warning(
                            "Unified Agent truncated delivery retry requested "
                            "run_id=%s mode=%s retries_remaining=%s "
                            "provider_request_id=%s",
                            run_id,
                            conversation_mode,
                            delivery_format_retries_remaining,
                            response.provider_request_id,
                        )
                        continue
                    final_error = "llm_output_truncated"
                    logger.warning(
                        "Unified Agent LLM output truncated run_id=%s mode=%s "
                        "content_length=%s tool_calls=%s provider_request_id=%s",
                        run_id,
                        conversation_mode,
                        len(response.text),
                        len(response.tool_calls),
                        response.provider_request_id,
                    )
                    break

                normalized_calls = self._normalize_calls(response.tool_calls)
                if normalized_calls:
                    agent_messages.append(
                        self._assistant_tool_call_message(response.text, normalized_calls)
                    )
                    for call in normalized_calls:
                        definition = self.registry.get(call.tool_name)
                        if (
                            not progress_reported
                            and conversation_mode == "call"
                            and on_progress_text is not None
                            and definition is not None
                            and call.tool_name in step_tool_names
                        ):
                            try:
                                definition.arguments_model.model_validate(call.arguments)
                            except Exception:
                                pass
                            else:
                                progress_text = build_call_progress_text(call.tool_name)
                                if progress_text:
                                    await on_progress_text(progress_text)
                                    progress_reported = True
                        if call.tool_name not in step_tool_names:
                            route_error = (
                                "tool_not_allowed_in_mode"
                                if definition is not None
                                and conversation_mode
                                not in definition.specification.allowed_modes
                                else "tool_not_allowed_for_route"
                            )
                            tool_result = AgentToolResult(
                                call_id=call.call_id,
                                tool_name=call.tool_name,
                                status=AgentToolStatus.FAILED,
                                arguments=call.arguments,
                                error_code=route_error,
                            )
                            tool_call_count += 1
                        elif tool_call_count >= maximum_tool_calls:
                            tool_result = AgentToolResult(
                                call_id=call.call_id,
                                tool_name=call.tool_name,
                                status=AgentToolStatus.FAILED,
                                arguments=call.arguments,
                                error_code="agent_tool_call_limit",
                            )
                        else:
                            tool_result = await asyncio.wait_for(
                                self.executor.execute(
                                    ToolExecutionContext(
                                        user_id=user_id,
                                        conversation_id=conversation_id,
                                        conversation_mode=conversation_mode,
                                        trigger_message=message,
                                        agent_turn_id=run_id,
                                        prior_results=tuple(tool_results),
                                    ),
                                    call,
                                ),
                                timeout=self._remaining_timeout(deadline),
                            )
                            tool_call_count += 1

                        tool_results.append(tool_result)
                        self._record_tool_result(
                            run_id,
                            user_id,
                            conversation_id,
                            call,
                            tool_result,
                        )
                        agent_messages.append(self._tool_result_message(tool_result))
                        sticker_placement = self._collect_delivery(
                            tool_result,
                            content_parts,
                            sources,
                            sticker_placement,
                        )
                        if tool_result.published_segments:
                            emitted_beats = tool_result.published_segments
                        next_scope = self.policy.next_tool_scope(
                            conversation_mode=conversation_mode,
                            tool_name=call.tool_name,
                            result=tool_result,
                        )
                        if next_scope is not None:
                            tools = (
                                self.registry.model_descriptions(
                                    conversation_mode, next_scope
                                )
                                if next_scope
                                else ()
                            )
                    if emitted_beats:
                        validate_agent_delivery_segments(emitted_beats)
                        return LoopOutcome(
                            completed=True,
                            text="\n".join(emitted_beats),
                            segments=emitted_beats,
                            content_parts=tuple(content_parts),
                            sources=tuple(sources),
                            tool_results=tuple(tool_results),
                            sticker_placement=sticker_placement,
                            model_steps=model_steps,
                            tool_calls=tool_call_count,
                        )
                    continue

                try:
                    delivery_plan = build_natural_delivery_plan(
                        response.text,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                        allow_empty=bool(content_parts) or profile.allow_empty_delivery,
                    )
                except AgentDeliveryPlanError as exc:
                    recovered_plan = self.gate.recover_metadata_prefix(
                        response.text,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                    )
                    if recovered_plan is not None:
                        delivery_plan = recovered_plan
                        logger.warning(
                            "Unified Agent metadata-prefixed natural delivery recovered "
                            "run_id=%s mode=%s content_length=%s prefix_codepoints=%s",
                            run_id,
                            conversation_mode,
                            len(response.text),
                            prefix_codepoints(response.text),
                        )
                    elif (
                        conversation_mode == "chat"
                        and delivery_format_retries_remaining > 0
                    ):
                        delivery_format_retries_remaining -= 1
                        agent_messages = self.gate.delivery_retry_messages(
                            agent_messages,
                        )
                        tools = ()
                        logger.warning(
                            "Unified Agent natural delivery retry requested "
                            "run_id=%s mode=%s retries_remaining=%s error_detail=%s "
                            "content_length=%s prefix_codepoints=%s",
                            run_id,
                            conversation_mode,
                            delivery_format_retries_remaining,
                            str(exc),
                            len(response.text),
                            prefix_codepoints(response.text),
                        )
                        continue
                    else:
                        deterministic_reply = (
                            self.fallbacks.call_tool_failure(tool_results)
                            if conversation_mode == "call"
                            else ""
                        ) or self.fallbacks.confirmation_for_completed_tool(tool_results)
                        if deterministic_reply:
                            delivery_plan = build_natural_delivery_plan(
                                deterministic_reply,
                                conversation_mode,
                                sticker_placement=sticker_placement,
                            )
                            logger.warning(
                                "Unified Agent natural delivery recovered from completed "
                                "side effect run_id=%s mode=%s",
                                run_id,
                                conversation_mode,
                            )
                        else:
                            logger.warning(
                                "Unified Agent natural delivery final rejection detail "
                                "run_id=%s mode=%s error_detail=%s content_length=%s "
                                "prefix_codepoints=%s",
                                run_id,
                                conversation_mode,
                                str(exc),
                                len(response.text),
                                prefix_codepoints(response.text),
                            )
                            raise
                if conversation_mode == "call":
                    deterministic_failure = self.fallbacks.call_tool_failure(
                        tool_results
                    )
                    if deterministic_failure:
                        delivery_plan = build_natural_delivery_plan(
                            deterministic_failure,
                            conversation_mode,
                            sticker_placement=sticker_placement,
                        )
                sticker_placement = delivery_plan.sticker_placement
                if (
                    conversation_mode == "proactive"
                    and not delivery_plan.text_segments
                    and not content_parts
                ):
                    return LoopOutcome(
                        completed=True,
                        text="",
                        segments=(),
                        content_parts=(),
                        sources=tuple(sources),
                        tool_results=tuple(tool_results),
                        sticker_placement=sticker_placement,
                        model_steps=model_steps,
                        tool_calls=tool_call_count,
                    )
                if (
                    conversation_mode in {"chat", "proactive"}
                    and delivery_plan.reply_text
                    and not self.gate.has_successful_sticker_delivery(
                        tool_results,
                        content_parts,
                    )
                    and self.gate.claims_sticker_delivery(delivery_plan.reply_text)
                ):
                    if (
                        sticker_claim_retries_remaining > 0
                        and model_steps < profile.max_steps
                    ):
                        sticker_claim_retries_remaining -= 1
                        agent_messages.append(
                            {"role": "assistant", "content": response.text.strip()}
                        )
                        agent_messages.append(
                            {
                                "role": "system",
                                "content": STICKER_CLAIM_RETRY_INSTRUCTION,
                            }
                        )
                        tools = ()
                        logger.warning(
                            "Unified Agent unbacked sticker delivery claim retry requested "
                            "run_id=%s retries_remaining=%s",
                            run_id,
                            sticker_claim_retries_remaining,
                        )
                        continue
                    delivery_plan = build_natural_delivery_plan(
                        self.fallbacks.no_sticker_reply(
                            tool_results,
                        ),
                        conversation_mode,
                        sticker_placement=sticker_placement,
                    )
                    logger.warning(
                        "Unified Agent unbacked sticker delivery claim replaced "
                        "deterministically run_id=%s",
                        run_id,
                    )
                if delivery_plan.text_segments or content_parts:
                    return LoopOutcome(
                        completed=True,
                        text=delivery_plan.reply_text,
                        segments=delivery_plan.text_segments,
                        content_parts=tuple(content_parts),
                        sources=tuple(sources),
                        tool_results=tuple(tool_results),
                        sticker_placement=sticker_placement,
                        model_steps=model_steps,
                        tool_calls=tool_call_count,
                    )

                agent_messages.append(
                    {
                        "role": "system",
                        "content": self.gate.final_retry_instruction(conversation_mode),
                    }
                )

            if profile.silent_on_failure and final_error is None:
                final_error = "agent_step_limit"
                logger.warning(
                    "Unified Agent proactive step limit reached; suppressing final retry "
                    "run_id=%s",
                    run_id,
                )
            if final_error is None:
                final_error = "agent_step_limit"
                fallback, _ = await self._try_final_response(
                    agent_messages,
                    deadline,
                    run_id,
                    llm_timeout_retries_remaining,
                    profile,
                )
                model_steps += 1
                if fallback:
                    delivery_plan = build_natural_delivery_plan(
                        fallback,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                        allow_empty=bool(content_parts),
                    )
                    if conversation_mode == "call":
                        deterministic_failure = self.fallbacks.call_tool_failure(
                            tool_results
                        )
                        if deterministic_failure:
                            delivery_plan = build_natural_delivery_plan(
                                deterministic_failure,
                                conversation_mode,
                                sticker_placement=sticker_placement,
                            )
                    if (
                        conversation_mode in {"chat", "proactive"}
                        and delivery_plan.reply_text
                        and not self.gate.has_successful_sticker_delivery(
                            tool_results,
                            content_parts,
                        )
                        and self.gate.claims_sticker_delivery(delivery_plan.reply_text)
                    ):
                        delivery_plan = build_natural_delivery_plan(
                            self.fallbacks.no_sticker_reply(
                                tool_results,
                            ),
                            conversation_mode,
                            sticker_placement=sticker_placement,
                        )
                        logger.warning(
                            "Unified Agent final fallback sticker claim replaced "
                            "deterministically run_id=%s",
                            run_id,
                        )
                    return LoopOutcome(
                        completed=True,
                        text=delivery_plan.reply_text,
                        segments=delivery_plan.text_segments,
                        content_parts=tuple(content_parts),
                        sources=tuple(sources),
                        tool_results=tuple(tool_results),
                        sticker_placement=sticker_placement,
                        model_steps=model_steps,
                        tool_calls=tool_call_count,
                        error_code=final_error,
                    )
                deterministic_reply = (
                    self.fallbacks.call_tool_failure(tool_results)
                    if conversation_mode == "call"
                    else ""
                ) or self.fallbacks.confirmation_for_completed_tool(tool_results)
                if deterministic_reply:
                    delivery_plan = build_natural_delivery_plan(
                        deterministic_reply,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                    )
                    return LoopOutcome(
                        completed=True,
                        text=delivery_plan.reply_text,
                        segments=delivery_plan.text_segments,
                        content_parts=tuple(content_parts),
                        sources=tuple(sources),
                        tool_results=tuple(tool_results),
                        sticker_placement=sticker_placement,
                        model_steps=model_steps,
                        tool_calls=tool_call_count,
                        error_code=final_error,
                    )
        except Exception as exc:
            if isinstance(exc, AgentDeliveryPlanError):
                final_error = exc.error_code
                logger.warning(
                    "Unified Agent natural delivery output rejected "
                    "run_id=%s mode=%s error_code=%s",
                    run_id,
                    conversation_mode,
                    final_error,
                )
            elif isinstance(exc, AgentModelTimeoutError):
                final_error = "llm_timeout"
            elif isinstance(exc, TimeoutError):
                final_error = "agent_timeout"
            else:
                final_error = type(exc).__name__
            logger.warning("Unified Agent runtime failed run_id=%s", run_id, exc_info=True)

        failed_content_parts = tuple(content_parts)
        if profile.silent_on_failure:
            # Background check-ins have no user turn to recover. A partial or
            # failed Agent result must stay silent instead of asking the user
            # to repeat a message they never sent.
            reply_text = ""
            failed_content_parts = ()
        else:
            reply_text = (
                self.fallbacks.call_tool_failure(tool_results)
                if conversation_mode == "call"
                else ""
            ) or self.fallbacks.disaster(content_parts)
        return LoopOutcome(
            completed=False,
            text=reply_text,
            segments=(reply_text,) if reply_text else (),
            content_parts=failed_content_parts,
            sources=tuple(sources),
            tool_results=tuple(tool_results),
            sticker_placement=sticker_placement,
            model_steps=model_steps,
            tool_calls=tool_call_count,
            error_code=final_error,
        )

    async def _try_final_response(
        self,
        messages: list[dict],
        deadline: float,
        run_id: str,
        timeout_retries_remaining: int,
        profile: TurnProfile,
    ) -> tuple[str, int]:
        try:
            response, timeout_retries_remaining = await self._complete_model(
                messages=[
                    *messages,
                    {
                        "role": "system",
                        "content": self.gate.final_retry_instruction(profile.mode),
                    },
                ],
                tools=(),
                structured_output=profile.structured_output,
                deadline=deadline,
                run_id=run_id,
                timeout_retries_remaining=timeout_retries_remaining,
            )
        except AgentModelTimeoutError:
            raise
        except Exception:
            return "", timeout_retries_remaining
        return (
            response.text.strip() if not response.tool_calls else "",
            timeout_retries_remaining,
        )

    async def _complete_model(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        structured_output: bool,
        deadline: float,
        run_id: str,
        timeout_retries_remaining: int,
        tool_choice: str | dict[str, Any] = "auto",
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[AgentModelResponse, int]:
        retried = False
        while True:
            try:
                completion_options: dict[str, Any] = {
                    "structured_output": structured_output,
                }
                if tool_choice != "auto":
                    completion_options["tool_choice"] = tool_choice
                # Do not speak speculative text from a tool-enabled model turn.
                # A provider may emit content before it finishes assembling a
                # tool call; only the final post-tool turn is safe for TTS.
                stream_callback = (
                    on_text_delta if on_text_delta is not None and not tools else None
                )
                if stream_callback is not None and hasattr(self.model, "stream_complete"):
                    response = await asyncio.wait_for(
                        self.model.stream_complete(
                            messages,
                            tools,
                            on_text_delta=stream_callback,
                            **completion_options,
                        ),
                        timeout=self._remaining_timeout(deadline),
                    )
                else:
                    response = await asyncio.wait_for(
                        self.model.complete(
                            messages,
                            tools,
                            **completion_options,
                        ),
                        timeout=self._remaining_timeout(deadline),
                    )
                return response, timeout_retries_remaining
            except AgentModelTimeoutError:
                remaining_seconds = deadline - asyncio.get_running_loop().time()
                can_retry = timeout_retries_remaining > 0 and remaining_seconds > 0.001
                logger.warning(
                    "Unified Agent LLM timeout run_id=%s retrying=%s retries_remaining=%s",
                    run_id,
                    can_retry,
                    timeout_retries_remaining,
                )
                if not can_retry:
                    raise
                timeout_retries_remaining -= 1
                retried = True
            except TimeoutError as exc:
                if retried:
                    raise AgentModelTimeoutError(
                        "Conversation model retry exceeded the Agent deadline"
                    ) from exc
                raise

    @staticmethod
    def _normalize_calls(calls: tuple[AgentToolCall, ...]) -> tuple[AgentToolCall, ...]:
        return tuple(
            AgentToolCall(
                call_id=call.call_id.strip() or f"tool_{uuid.uuid4().hex}",
                tool_name=call.tool_name.strip(),
                arguments=call.arguments,
            )
            for call in calls
        )

    @staticmethod
    def _assistant_tool_call_message(
        text: str,
        calls: tuple[AgentToolCall, ...],
    ) -> dict:
        return {
            "role": "assistant",
            "content": text,
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.tool_name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in calls
            ],
        }

    @staticmethod
    def _tool_result_message(result: AgentToolResult) -> dict:
        safe_result: object = result.safe_for_model
        if result.safe_for_model:
            with suppress(json.JSONDecodeError):
                safe_result = json.loads(result.safe_for_model)
        payload = {
            "status": result.status.value,
            "result": safe_result,
            "error_code": result.error_code,
        }
        return {
            "role": "tool",
            "tool_call_id": result.call_id,
            "content": json.dumps(payload, ensure_ascii=False),
        }

    @staticmethod
    def _collect_delivery(
        result: AgentToolResult,
        content_parts: list[ContentPart],
        sources: list[SourceReference],
        sticker_placement: str,
    ) -> str:
        if result.status != AgentToolStatus.COMPLETED:
            return sticker_placement
        accepts_sticker = result.sticker_placement is not None
        existing_stickers = {part.sticker_id for part in content_parts if part.sticker_id}
        content_parts.extend(
            part
            for part in result.content_parts
            if part.type != "sticker" or accepts_sticker
            if not part.sticker_id or part.sticker_id not in existing_stickers
        )
        existing_urls = {source.url for source in sources}
        sources.extend(source for source in result.sources if source.url not in existing_urls)
        if result.sticker_placement in {"before_text", "after_text"}:
            return result.sticker_placement
        return sticker_placement

    @staticmethod
    def _remaining_timeout(deadline: float) -> float:
        return max(deadline - asyncio.get_running_loop().time(), 0.001)

    def _record_tool_result(
        self,
        run_id: str,
        user_id: str,
        conversation_id: str | None,
        call: AgentToolCall,
        result: AgentToolResult,
    ) -> None:
        self.repository.record_tool_call(
            run_id,
            call.tool_name,
            call.arguments,
            result.data,
            result.error_code,
            status=result.status.value,
            tool_call_id=call.call_id,
        )
        try:
            from features.conversation_events.public import (
                ACTOR_ECHO,
                EVENT_TOOL_CALL,
                record_conversation_event,
            )

            record_conversation_event(
                event_type=EVENT_TOOL_CALL,
                source="agent",
                actor=ACTOR_ECHO,
                user_id=user_id,
                conversation_id=conversation_id,
                turn_id=run_id,
                content=f"{call.tool_name} {result.status.value}",
                payload={
                    "tool_name": call.tool_name,
                    "status": result.status.value,
                    "error_code": result.error_code or "",
                    "arguments": call.arguments,
                },
            )
        except Exception:
            logger.warning("record tool call event failed", exc_info=True)
