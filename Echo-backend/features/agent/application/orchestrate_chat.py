from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from contextlib import suppress
from typing import Any

from features.agent.application.execute_tool import ToolExecutor
from features.agent.domain.delivery import (
    AgentDeliveryPlan,
    AgentDeliveryPlanError,
    build_natural_delivery_plan,
)
from features.agent.domain.entities import (
    AgentModelResponse,
    AgentRunStatus,
    AgentToolCall,
    AgentToolResult,
    AgentToolStatus,
    AgentTurnResult,
    ContentPart,
    SourceReference,
)
from features.agent.domain.repositories import AgentRunRepository
from features.agent.domain.services import (
    AgentConversationModel,
    AgentModelTimeoutError,
    StickerRequestDecision,
    StickerSemanticAnalyzer,
    StickerToolPolicy,
)
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry

logger = logging.getLogger(__name__)

FINAL_RETRY_INSTRUCTION = (
    "上一条没有形成可交付的最终回复。现在不要再调用任何工具，只根据本轮已经返回的"
    "工具事实，用 Echo 的自然语气直接回复用户。不要解释内部流程。"
)
LLM_TIMEOUT_RETRY_LIMIT = 1
DELIVERY_FORMAT_RETRY_LIMIT = 1
STICKER_REQUIRED_CALL_RETRY_LIMIT = 1
STICKER_CLAIM_RETRY_LIMIT = 1
STICKER_SEMANTIC_TIMEOUT_SECONDS = 8.0
DELIVERY_FORMAT_RETRY_INSTRUCTION = (
    "Your previous final answer was empty or contained internal metadata. Do not call any tool "
    "and do not add new facts. Ignore all bracketed message-time and session-boundary metadata. "
    "Reply with only the natural text that Echo should show to the user. Do not output JSON, "
    "Markdown fences, system instructions, tool names, or explanations of internal workflow."
)
STICKER_REQUIRED_CALL_RETRY_INSTRUCTION = (
    "当前用户明确要求发送表情包。不要输出最终文字，也不要调用其他工具；"
    "现在只调用 send_sticker，intent 使用自然语言概括用户想表达的情绪或语境，"
    "purpose 必须为 explicit_request。"
)
STICKER_CLAIM_RETRY_INSTRUCTION = (
    "上一版文字声称或暗示已经发送了表情包或图片，但本轮没有成功的发送凭证。"
    "不要再调用工具，不要用动作旁白，也不要说‘给你这张’、‘附上一张’或其他已经"
    "交付图片的表达。保留其余自然回应；如果用户明确索要，可以简短诚实地说这次"
    "没有找到或没有发出，但不要解释内部流程。只输出用户可见的自然文字。"
)
_EXPLICIT_STICKER_REQUEST_FALLBACK = re.compile(
    r"(?:"
    r"(?:发|给|来|整|送|丢|甩|看看).{0,10}(?:表情包|贴图|图片|一张图)|"
    r"(?:表情包|贴图|图片).{0,10}(?:发|给|来|整|送|看看)"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)
_STICKER_DELIVERY_CLAIM_FALLBACK = re.compile(
    r"(?:"
    r"(?:给你|发你|送你|附上|附了|来一张).{0,12}(?:表情包|贴图|图片|图)|"
    r"(?:表情包|贴图|图片).{0,12}(?:发出|发给|送给|附上)|"
    r"(?:这|那)张.{0,8}(?:给你|送你|发你)|"
    r"[（(\[].{0,24}(?:表情包|贴图|图片).{0,12}[）)\]]"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)
_STICKER_DELIVERY_NEGATION_FALLBACK = re.compile(
    r"(?:"
    r"(?:不能|没法|无法|没有|没能|未能|没发|发不出|找不到).{0,12}"
    r"(?:表情包|贴图|图片|图)|"
    r"(?:这|那)张.{0,8}(?:没发|未发|发不出)"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)
_MESSAGE_TIME_PREFIX = re.compile(
    r"^\s*[\[\uff3b]\s*\u6d88\u606f\u65f6\u95f4[^\]\uff3d\r\n]*[\]\uff3d]\s*(?:\r?\n)?"
)
_SESSION_BOUNDARY_PREFIX = re.compile(
    r"^\s*[\[\uff3b]\s*\u4f1a\u8bdd\u65f6\u95f4\u8fb9\u754c[\]\uff3d]"
)
_SESSION_BOUNDARY_LINE = re.compile(
    r"^\s*[\[\uff3b]\s*\u4f1a\u8bdd\u65f6\u95f4\u8fb9\u754c[\]\uff3d]"
    r"[^\r\n]*(?:\r?\n)?"
)


class OrchestrateChatWithAgent:
    def __init__(
        self,
        repository: AgentRunRepository,
        model: AgentConversationModel,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_steps: int,
        max_tool_calls: int,
        run_timeout_seconds: int,
        sticker_semantic_analyzer: StickerSemanticAnalyzer | None = None,
    ):
        self.repository = repository
        self.model = model
        self.registry = registry
        self.executor = executor
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.run_timeout_seconds = run_timeout_seconds
        self.sticker_semantic_analyzer = sticker_semantic_analyzer

    async def execute(
        self,
        user_id: str,
        message: str,
        messages: list[dict],
        conversation_id: str | None = None,
        conversation_mode: str = "chat",
        sticker_intent: str = "",
        allow_proactive_stickers: bool = True,
        proactive_sticker_due: bool = False,
        tools_enabled: bool = True,
    ) -> AgentTurnResult:
        run_id = self.repository.start(user_id, message, conversation_mode, self.max_steps)
        agent_messages = self._build_initial_messages(
            messages=messages,
            conversation_mode=conversation_mode,
            sticker_intent=sticker_intent,
            allow_proactive_stickers=allow_proactive_stickers,
            proactive_sticker_due=proactive_sticker_due,
        )
        tool_results: list[AgentToolResult] = []
        content_parts: list[ContentPart] = []
        sources: list[SourceReference] = []
        sticker_placement = "after_text"
        model_steps = 0
        tool_call_count = 0
        llm_timeout_retries_remaining = LLM_TIMEOUT_RETRY_LIMIT
        delivery_format_retries_remaining = DELIVERY_FORMAT_RETRY_LIMIT
        required_call_retries_remaining = STICKER_REQUIRED_CALL_RETRY_LIMIT
        sticker_claim_retries_remaining = STICKER_CLAIM_RETRY_LIMIT
        final_error: str | None = None
        deadline = asyncio.get_running_loop().time() + self.run_timeout_seconds
        tools = self.registry.model_descriptions(conversation_mode) if tools_enabled else ()
        sticker_decision = StickerRequestDecision(StickerToolPolicy.OPTIONAL)
        required_sticker_call_pending = False

        try:
            sticker_decision = await self._resolve_sticker_policy(
                message=message,
                messages=messages,
                conversation_mode=conversation_mode,
                tools=tools,
                deadline=deadline,
                run_id=run_id,
            )
            required_sticker_call_pending = (
                sticker_decision.policy == StickerToolPolicy.REQUIRED
            )
            while model_steps < self.max_steps:
                model_steps += 1
                tool_choice = (
                    self._forced_tool_choice("send_sticker")
                    if required_sticker_call_pending and tools
                    else "auto"
                )
                response, llm_timeout_retries_remaining = await self._complete_model(
                    messages=agent_messages,
                    tools=tools,
                    structured_output=conversation_mode == "daily_letter",
                    tool_choice=tool_choice,
                    deadline=deadline,
                    run_id=run_id,
                    timeout_retries_remaining=llm_timeout_retries_remaining,
                )

                finish_reason = response.finish_reason.strip().lower()
                if finish_reason == "length" and (
                    conversation_mode == "daily_letter" or not response.text.strip()
                ):
                    if (
                        conversation_mode in {"chat", "proactive"}
                        and delivery_format_retries_remaining > 0
                    ):
                        delivery_format_retries_remaining -= 1
                        agent_messages = self._delivery_retry_messages(
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
                if required_sticker_call_pending:
                    required_calls = tuple(
                        call for call in normalized_calls if call.tool_name == "send_sticker"
                    )
                    if not required_calls:
                        if (
                            required_call_retries_remaining > 0
                            and model_steps < self.max_steps
                        ):
                            required_call_retries_remaining -= 1
                            agent_messages.append(
                                {
                                    "role": "system",
                                    "content": STICKER_REQUIRED_CALL_RETRY_INSTRUCTION,
                                }
                            )
                            logger.warning(
                                "Unified Agent required sticker call retry requested "
                                "run_id=%s retries_remaining=%s returned_tool_calls=%s",
                                run_id,
                                required_call_retries_remaining,
                                [call.tool_name for call in normalized_calls],
                            )
                            continue
                        required_calls = (
                            AgentToolCall(
                                call_id=f"required_sticker_{uuid.uuid4().hex}",
                                tool_name="send_sticker",
                                arguments={
                                    "intent": sticker_decision.intent or message[:300],
                                    "purpose": "explicit_request",
                                    "placement": "after_text",
                                },
                            ),
                        )
                        logger.warning(
                            "Unified Agent required sticker call synthesized after invalid "
                            "function response run_id=%s",
                            run_id,
                        )
                    normalized_calls = (
                        self._normalize_required_sticker_call(
                            required_calls[0],
                            sticker_decision,
                            message,
                        ),
                    )
                    required_sticker_call_pending = False

                if normalized_calls:
                    agent_messages.append(
                        self._assistant_tool_call_message(response.text, normalized_calls)
                    )
                    for call in normalized_calls:
                        if tool_call_count >= self.max_tool_calls:
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
                                        allow_proactive_stickers=allow_proactive_stickers,
                                        prior_results=tuple(tool_results),
                                    ),
                                    call,
                                ),
                                timeout=self._remaining_timeout(deadline),
                            )
                            definition = self.registry.get(call.tool_name)
                            if not (
                                definition is not None
                                and not definition.specification.count_no_result_toward_call_limit
                                and tool_result.status == AgentToolStatus.NO_RESULT
                            ):
                                tool_call_count += 1

                        tool_results.append(tool_result)
                        self._record_tool_result(run_id, call, tool_result)
                        agent_messages.append(self._tool_result_message(tool_result))
                        sticker_placement = self._collect_delivery(
                            tool_result,
                            content_parts,
                            sources,
                            sticker_placement,
                        )
                    continue

                try:
                    delivery_plan = build_natural_delivery_plan(
                        response.text,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                        allow_empty=bool(content_parts),
                    )
                except AgentDeliveryPlanError as exc:
                    recovered_plan = self._recover_metadata_prefixed_delivery(
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
                            self._prefix_codepoints(response.text),
                        )
                    elif (
                        conversation_mode in {"chat", "proactive"}
                        and delivery_format_retries_remaining > 0
                    ):
                        delivery_format_retries_remaining -= 1
                        agent_messages = self._delivery_retry_messages(
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
                            self._prefix_codepoints(response.text),
                        )
                        continue
                    else:
                        deterministic_reply = self._deterministic_tool_confirmation(
                            tool_results
                        )
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
                                self._prefix_codepoints(response.text),
                            )
                            raise
                sticker_placement = delivery_plan.sticker_placement
                if (
                    conversation_mode in {"chat", "proactive"}
                    and delivery_plan.reply_text
                    and not self._has_successful_sticker_delivery(
                        tool_results,
                        content_parts,
                    )
                    and await self._claims_sticker_delivery(
                        delivery_plan.reply_text,
                        deadline=deadline,
                        run_id=run_id,
                    )
                ):
                    if (
                        sticker_claim_retries_remaining > 0
                        and model_steps < self.max_steps
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
                        required_sticker_call_pending = False
                        logger.warning(
                            "Unified Agent unbacked sticker delivery claim retry requested "
                            "run_id=%s retries_remaining=%s",
                            run_id,
                            sticker_claim_retries_remaining,
                        )
                        continue
                    delivery_plan = build_natural_delivery_plan(
                        self._deterministic_no_sticker_reply(
                            tool_results,
                            explicit_request=(
                                sticker_decision.policy == StickerToolPolicy.REQUIRED
                            ),
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
                    result = AgentTurnResult(
                        status=AgentRunStatus.COMPLETED,
                        reply_text=delivery_plan.reply_text,
                        sources=tuple(sources),
                        content_parts=tuple(content_parts),
                        tool_results=tuple(tool_results),
                        run_id=run_id,
                        model_steps=model_steps,
                        reply_segments=delivery_plan.text_segments,
                        sticker_placement=sticker_placement,
                    )
                    self.repository.finish(run_id, model_steps + tool_call_count)
                    return result

                agent_messages.append(
                    {
                        "role": "system",
                        "content": self._final_retry_instruction(conversation_mode),
                    }
                )

            if final_error is None:
                final_error = "agent_step_limit"
                fallback, _ = await self._try_final_response(
                    agent_messages,
                    deadline,
                    run_id,
                    llm_timeout_retries_remaining,
                    conversation_mode,
                )
                model_steps += 1
                if fallback:
                    delivery_plan = build_natural_delivery_plan(
                        fallback,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                        allow_empty=bool(content_parts),
                    )
                    if (
                        conversation_mode in {"chat", "proactive"}
                        and delivery_plan.reply_text
                        and not self._has_successful_sticker_delivery(
                            tool_results,
                            content_parts,
                        )
                        and await self._claims_sticker_delivery(
                            delivery_plan.reply_text,
                            deadline=deadline,
                            run_id=run_id,
                        )
                    ):
                        delivery_plan = build_natural_delivery_plan(
                            self._deterministic_no_sticker_reply(
                                tool_results,
                                explicit_request=(
                                    sticker_decision.policy == StickerToolPolicy.REQUIRED
                                ),
                            ),
                            conversation_mode,
                            sticker_placement=sticker_placement,
                        )
                        logger.warning(
                            "Unified Agent final fallback sticker claim replaced "
                            "deterministically run_id=%s",
                            run_id,
                        )
                    result = AgentTurnResult(
                        status=AgentRunStatus.COMPLETED,
                        reply_text=delivery_plan.reply_text,
                        sources=tuple(sources),
                        content_parts=tuple(content_parts),
                        tool_results=tuple(tool_results),
                        run_id=run_id,
                        model_steps=model_steps,
                        error_code=final_error,
                        reply_segments=delivery_plan.text_segments,
                        sticker_placement=sticker_placement,
                    )
                    self.repository.finish(run_id, model_steps + tool_call_count, final_error)
                    return result
                deterministic_reply = self._deterministic_tool_confirmation(tool_results)
                if deterministic_reply:
                    delivery_plan = build_natural_delivery_plan(
                        deterministic_reply,
                        conversation_mode,
                        sticker_placement=sticker_placement,
                    )
                    result = AgentTurnResult(
                        status=AgentRunStatus.COMPLETED,
                        reply_text=delivery_plan.reply_text,
                        sources=tuple(sources),
                        content_parts=tuple(content_parts),
                        tool_results=tuple(tool_results),
                        run_id=run_id,
                        model_steps=model_steps,
                        error_code=final_error,
                        reply_segments=delivery_plan.text_segments,
                        sticker_placement=sticker_placement,
                    )
                    self.repository.finish(run_id, model_steps + tool_call_count, final_error)
                    return result
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
        if conversation_mode == "proactive":
            # Background check-ins have no user turn to recover. A partial or
            # failed Agent result must stay silent instead of asking the user
            # to repeat a message they never sent.
            reply_text = ""
            failed_content_parts = ()
        else:
            reply_text = self._disaster_fallback(content_parts)
        self.repository.finish(run_id, model_steps + tool_call_count, final_error)
        return AgentTurnResult(
            status=AgentRunStatus.FAILED,
            reply_text=reply_text,
            sources=tuple(sources),
            content_parts=failed_content_parts,
            tool_results=tuple(tool_results),
            run_id=run_id,
            model_steps=model_steps,
            error_code=final_error,
            reply_segments=(reply_text,) if reply_text else (),
        )

    async def _try_final_response(
        self,
        messages: list[dict],
        deadline: float,
        run_id: str,
        timeout_retries_remaining: int,
        conversation_mode: str,
    ) -> tuple[str, int]:
        try:
            response, timeout_retries_remaining = await self._complete_model(
                messages=[
                    *messages,
                    {
                        "role": "system",
                        "content": self._final_retry_instruction(conversation_mode),
                    },
                ],
                tools=(),
                structured_output=conversation_mode == "daily_letter",
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

    @staticmethod
    def _final_retry_instruction(conversation_mode: str) -> str:
        if conversation_mode in {"chat", "proactive"}:
            return FINAL_RETRY_INSTRUCTION + DELIVERY_FORMAT_RETRY_INSTRUCTION
        return FINAL_RETRY_INSTRUCTION

    @staticmethod
    def _delivery_retry_messages(messages: list[dict]) -> list[dict]:
        sanitized = OrchestrateChatWithAgent._sanitize_time_metadata(messages)
        sanitized.append(
            {
                "role": "system",
                "content": DELIVERY_FORMAT_RETRY_INSTRUCTION,
            }
        )
        return sanitized

    @staticmethod
    def _recover_metadata_prefixed_delivery(
        text: str,
        conversation_mode: str,
        *,
        sticker_placement: str = "after_text",
    ) -> AgentDeliveryPlan | None:
        if conversation_mode != "chat":
            return None
        candidate = text.strip()
        removed_metadata = False
        while candidate:
            without_message_time = _MESSAGE_TIME_PREFIX.sub("", candidate, count=1)
            if without_message_time != candidate:
                candidate = without_message_time.strip()
                removed_metadata = True
                continue
            without_boundary = _SESSION_BOUNDARY_LINE.sub("", candidate, count=1)
            if without_boundary != candidate:
                candidate = without_boundary.strip()
                removed_metadata = True
                continue
            break
        if not removed_metadata or not candidate:
            return None
        try:
            return build_natural_delivery_plan(
                candidate,
                conversation_mode,
                sticker_placement=sticker_placement,
                allow_empty=False,
            )
        except AgentDeliveryPlanError:
            if candidate.startswith(("{", "[", "```")):
                return None
            return None

    @staticmethod
    def _sanitize_time_metadata(messages: list[dict]) -> list[dict]:
        sanitized: list[dict] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, str):
                sanitized.append(dict(message))
                continue
            if message.get("role") == "system" and _SESSION_BOUNDARY_PREFIX.match(content):
                continue
            sanitized.append(
                {
                    **message,
                    "content": _MESSAGE_TIME_PREFIX.sub("", content, count=1),
                }
            )
        return sanitized

    @staticmethod
    def _prefix_codepoints(text: str, limit: int = 8) -> str:
        return ",".join(f"U+{ord(character):04X}" for character in text[:limit])

    async def _complete_model(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        structured_output: bool,
        deadline: float,
        run_id: str,
        timeout_retries_remaining: int,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> tuple[AgentModelResponse, int]:
        retried = False
        while True:
            try:
                completion_options: dict[str, Any] = {
                    "structured_output": structured_output,
                }
                if tool_choice != "auto":
                    completion_options["tool_choice"] = tool_choice
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

    async def _resolve_sticker_policy(
        self,
        *,
        message: str,
        messages: list[dict],
        conversation_mode: str,
        tools: tuple[dict, ...],
        deadline: float,
        run_id: str,
    ) -> StickerRequestDecision:
        tool_names = {
            str(item.get("function", {}).get("name") or "") for item in tools
        }
        if conversation_mode in {"call", "daily_letter"} or "send_sticker" not in tool_names:
            return StickerRequestDecision(StickerToolPolicy.FORBIDDEN)
        if conversation_mode == "proactive":
            return StickerRequestDecision(StickerToolPolicy.OPTIONAL)
        if self.sticker_semantic_analyzer is None:
            return StickerRequestDecision(StickerToolPolicy.OPTIONAL)
        try:
            decision = await asyncio.wait_for(
                self.sticker_semantic_analyzer.assess_request(message, messages),
                timeout=min(
                    self._remaining_timeout(deadline),
                    STICKER_SEMANTIC_TIMEOUT_SECONDS,
                ),
            )
            if decision.policy not in {
                StickerToolPolicy.REQUIRED,
                StickerToolPolicy.OPTIONAL,
            }:
                raise ValueError("Sticker request analyzer returned an invalid policy")
            return decision
        except Exception as exc:
            fallback_required = bool(
                _EXPLICIT_STICKER_REQUEST_FALLBACK.search(message)
            )
            logger.warning(
                "Sticker request semantic analysis failed run_id=%s fallback_required=%s "
                "error_type=%s",
                run_id,
                fallback_required,
                type(exc).__name__,
            )
            return StickerRequestDecision(
                StickerToolPolicy.REQUIRED
                if fallback_required
                else StickerToolPolicy.OPTIONAL,
                message.strip()[:300] if fallback_required else "",
            )

    async def _claims_sticker_delivery(
        self,
        reply_text: str,
        *,
        deadline: float,
        run_id: str,
    ) -> bool:
        if self.sticker_semantic_analyzer is not None:
            try:
                return await asyncio.wait_for(
                    self.sticker_semantic_analyzer.claims_sticker_delivery(reply_text),
                    timeout=min(
                        self._remaining_timeout(deadline),
                        STICKER_SEMANTIC_TIMEOUT_SECONDS,
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "Sticker delivery claim semantic analysis failed run_id=%s "
                    "error_type=%s",
                    run_id,
                    type(exc).__name__,
                )
        if _STICKER_DELIVERY_NEGATION_FALLBACK.search(reply_text):
            return False
        return bool(_STICKER_DELIVERY_CLAIM_FALLBACK.search(reply_text))

    @staticmethod
    def _forced_tool_choice(tool_name: str) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": tool_name},
        }

    @staticmethod
    def _normalize_required_sticker_call(
        call: AgentToolCall,
        decision: StickerRequestDecision,
        message: str,
    ) -> AgentToolCall:
        requested_placement = str(call.arguments.get("placement") or "").strip()
        return AgentToolCall(
            call_id=call.call_id,
            tool_name="send_sticker",
            arguments={
                "intent": (
                    str(call.arguments.get("intent") or "").strip()
                    or decision.intent
                    or message.strip()
                )[:300],
                "purpose": "explicit_request",
                "placement": (
                    requested_placement
                    if requested_placement in {"before_text", "after_text"}
                    else "after_text"
                ),
            },
        )

    @staticmethod
    def _has_successful_sticker_delivery(
        results: list[AgentToolResult],
        content_parts: list[ContentPart],
    ) -> bool:
        delivered_ids = {
            part.sticker_id
            for part in content_parts
            if part.type == "sticker" and part.sticker_id
        }
        return any(
            result.tool_name == "send_sticker"
            and result.status == AgentToolStatus.COMPLETED
            and bool(result.data.get("sent"))
            and str(result.data.get("sticker_id") or "") in delivered_ids
            for result in results
        )

    @staticmethod
    def _deterministic_no_sticker_reply(
        results: list[AgentToolResult],
        *,
        explicit_request: bool,
    ) -> str:
        sticker_results = [
            result for result in results if result.tool_name == "send_sticker"
        ]
        if any(result.status == AgentToolStatus.NO_RESULT for result in sticker_results):
            return "这次没找到合适的表情包，我先不乱发。"
        if sticker_results or explicit_request:
            return "这次表情包没有发出去，我们先继续聊。"
        return "我在，继续和你说。"

    @staticmethod
    def _build_initial_messages(
        messages: list[dict],
        conversation_mode: str,
        sticker_intent: str,
        allow_proactive_stickers: bool,
        proactive_sticker_due: bool,
    ) -> list[dict]:
        if conversation_mode == "call":
            sticker_rule = (
                "当前是语音通话模式。不得搜索、选择或发送表情包，即使用户明确要求也不"
                "执行图片发送；自然说明通话里先继续说话即可。"
            )
        elif conversation_mode == "daily_letter":
            sticker_rule = (
                "当前是每日来信模式，不得搜索、选择或发送聊天表情包，也不得创建定时任务、"
                "主动聊天或外部搜索。图片只通过结构化 image_brief 交给来信业务处理。"
            )
        elif conversation_mode == "proactive":
            sticker_rule = (
                "This run was triggered by background policy, not by a new user message. "
                "Never state or imply that the user is awake, online, reading, responding, "
                "energetic, available, or currently doing something merely because this "
                "task is running. Use conditional wording when their current state is "
                "unknown. This is a proactive text chat. Use at most one fitting sticker "
                "only when "
                "it naturally improves a light, everyday check-in. Never use a sticker to "
                "force warmth or compensate for a weak topic."
            )
        elif allow_proactive_stickers and proactive_sticker_due:
            sticker_rule = (
                "聊天模式可以使用表情包。用户明确要求时调用 send_sticker，purpose 使用 "
                "explicit_request。当前回合进入主动表情包优先窗口；如果当前是轻松、日常或"
                "适合表达情绪的语境，应主动调用 send_sticker，purpose 使用 proactive，intent "
                "用自然语言描述想表达的情绪和语境。官方和用户"
                "私人表情包都可以参与选择。严肃、安全、医疗、冲突或明显悲伤的话题可以暂缓，"
                "不要为了完成频率要求而破坏语境。"
            )
        elif allow_proactive_stickers:
            sticker_rule = (
                "聊天模式可以使用表情包。用户明确要求时调用 send_sticker，purpose 使用 "
                "explicit_request。轻松且确实合适时可以主动附带一张，purpose 使用 proactive，"
                "intent 用自然语言描述表达意图；严肃、安全、医疗、冲突或明显悲伤时不要主动发送。"
            )
        else:
            sticker_rule = (
                "聊天模式可以响应用户明确的表情包请求，purpose 使用 explicit_request。"
                "当前处于主动表情包冷却期，不得以 proactive 为 purpose 调用表情包工具。"
            )
        delivery_rule = ""
        if conversation_mode in {"chat", "proactive"}:
            delivery_rule = (
                "FINAL DELIVERY CONTRACT: After you finish tool calls, output only the natural "
                "user-visible reply. Do not output JSON, Markdown fences, tool names, internal "
                "metadata, or explanations of the Agent workflow. Use a blank line when a reply "
                "naturally reads as separate chat messages; otherwise keep it as one message. "
                "Most replies should still use one to three messages. Use more only when the reply "
                "contains genuinely distinct thoughts, and never exceed six. If send_sticker "
                "completed, the backend will attach the image separately and you must not claim "
                "that you cannot send it. A sticker is sent only when send_sticker completes. "
                "Never narrate or simulate sticker/image delivery in visible text, including "
                "parenthesized, bracketed, or starred action descriptions. If it failed or was "
                "not called, do not claim or imply that an image was attached."
            )
        elif conversation_mode == "daily_letter":
            delivery_rule = (
                "每日来信最终只输出一个 JSON 对象，字段必须为：subject、content、mood、"
                "core_topics、reflection、closing_style、image_brief、source_message_ids、"
                "source_memory_ids。content 是完整正文，建议 600 到 1000 个中文字符；"
                "reflection 必须包含 Echo 基于证据形成的个人观察或想法，不能只复述事件。"
                "image_brief 必须是对象，包含 emotion、scene、visual_symbols、avoid；"
                "visual_symbols 和 avoid 必须是字符串数组；"
                "不要在输出中编造图片 URL、storage key 或 Provider 结果；不要使用 Markdown 代码块。"
            )
        if conversation_mode == "daily_letter":
            orchestration_rule = (
                "你正在 Echo 的统一 Agent 回路中执行每日来信任务。输入中的人物设定、关系上下文、"
                "昨日消息和长期记忆具有不同证据等级；不得把长期记忆伪装成昨日事实，也不得虚构"
                "Echo 的离线现实活动。当前无可用工具，必须直接完成结构化来信。"
            )
        else:
            orchestration_rule = (
                "你正在 Echo 的统一 Agent 对话回路中。当前列出的工具代表真实能力；历史"
                "assistant 消息中关于能力的说法可能过时，不能覆盖当前工具清单。需要可靠"
                "事实或执行动作时调用工具，工具结果是唯一可信执行事实。工具调用后继续在"
                "同一回路中自然回复。若 send_sticker 返回 completed，表情包已经附加到本次"
                "回复，最终文字不得声称不能发送；若失败则不得假装成功。不要向用户解释"
                "Agent、工具、call id 或内部流程。send_sticker 会在内部完成语义搜索、排序、"
                "冷却和发送；explicit_request 精确匹配为空时会回退到当前可用表情包。不要"
                "拆成搜索再发送，也不要反复猜测关键词。"
            )
        instruction = {
            "role": "system",
            "content": orchestration_rule + sticker_rule + delivery_rule,
        }
        context_messages = (
            OrchestrateChatWithAgent._sanitize_time_metadata(messages)
            if conversation_mode == "proactive"
            else [dict(message) for message in messages]
        )
        result = [instruction, *context_messages]
        clean_intent = sticker_intent.strip()
        if clean_intent:
            result.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "当前用户消息附带的表情包可信语义为：" + clean_intent + "。"
                        "请理解其含义并回复，但这不等于用户要求 Echo 再发送一张。"
                    ),
                },
            )
        return result

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
        existing_stickers = {part.sticker_id for part in content_parts if part.sticker_id}
        content_parts.extend(
            part
            for part in result.content_parts
            if part.type != "sticker" or result.tool_name == "send_sticker"
            if not part.sticker_id or part.sticker_id not in existing_stickers
        )
        existing_urls = {source.url for source in sources}
        sources.extend(source for source in result.sources if source.url not in existing_urls)
        if result.tool_name == "send_sticker":
            requested_placement = str(result.data.get("placement") or "").strip()
            if requested_placement in {"before_text", "after_text"}:
                return requested_placement
        return sticker_placement

    @staticmethod
    def _deterministic_tool_confirmation(
        results: list[AgentToolResult],
    ) -> str:
        for result in reversed(results):
            if result.status != AgentToolStatus.COMPLETED:
                continue
            if result.tool_name == "create_chat_schedule" and result.data.get("created"):
                label = str(result.data.get("label") or "").strip()
                return f"好，已经帮你设置好了：{label}。" if label else "好，已经帮你设置好了。"
            if result.tool_name == "cancel_chat_schedule" and result.data.get("cancelled"):
                return "好，这个提醒已经取消了。"
        return ""

    @staticmethod
    def _disaster_fallback(content_parts: list[ContentPart]) -> str:
        if any(part.type == "sticker" for part in content_parts):
            return "这张给你。"
        return "刚才这次回复没有完成，再和我说一次好吗？"

    @staticmethod
    def _remaining_timeout(deadline: float) -> float:
        return max(deadline - asyncio.get_running_loop().time(), 0.001)

    def _record_tool_result(
        self,
        run_id: str,
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
