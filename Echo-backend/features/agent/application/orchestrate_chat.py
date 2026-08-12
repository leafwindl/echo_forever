from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from features.agent.application.execute_tool import ToolExecutor
from features.agent.domain.delivery import AgentDeliveryPlanError, parse_agent_delivery_plan
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
from features.agent.domain.services import AgentConversationModel, AgentModelTimeoutError
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry

logger = logging.getLogger(__name__)

FINAL_RETRY_INSTRUCTION = (
    "上一条没有形成可交付的最终回复。现在不要再调用任何工具，只根据本轮已经返回的"
    "工具事实，用 Echo 的自然语气直接回复用户。不要解释内部流程。"
)
LLM_TIMEOUT_RETRY_LIMIT = 1
DELIVERY_FORMAT_RETRY_LIMIT = 1
DELIVERY_FORMAT_RETRY_INSTRUCTION = (
    "Your previous final answer failed the delivery contract. Do not call any tool and do "
    "not add new content. Return exactly one JSON object with only text_segments and "
    "sticker_placement. text_segments must contain zero to three unique, non-empty strings; "
    "sticker_placement must be before_text or after_text. Output no Markdown or surrounding text."
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
    ):
        self.repository = repository
        self.model = model
        self.registry = registry
        self.executor = executor
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.run_timeout_seconds = run_timeout_seconds

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
        model_steps = 0
        tool_call_count = 0
        llm_timeout_retries_remaining = LLM_TIMEOUT_RETRY_LIMIT
        delivery_format_retries_remaining = DELIVERY_FORMAT_RETRY_LIMIT
        final_error: str | None = None
        deadline = asyncio.get_running_loop().time() + self.run_timeout_seconds
        tools = self.registry.model_descriptions(conversation_mode) if tools_enabled else ()

        try:
            while model_steps < self.max_steps:
                model_steps += 1
                response, llm_timeout_retries_remaining = await self._complete_model(
                    messages=agent_messages,
                    tools=tools,
                    structured_output=conversation_mode in {"chat", "proactive"},
                    deadline=deadline,
                    run_id=run_id,
                    timeout_retries_remaining=llm_timeout_retries_remaining,
                )

                finish_reason = response.finish_reason.strip().lower()
                if finish_reason == "length" and (
                    conversation_mode == "daily_letter" or not response.text.strip()
                ):
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

                if response.tool_calls:
                    normalized_calls = self._normalize_calls(response.tool_calls)
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
                        self._collect_delivery(tool_result, content_parts, sources)
                    continue

                try:
                    delivery_plan = parse_agent_delivery_plan(response.text, conversation_mode)
                except AgentDeliveryPlanError:
                    if (
                        conversation_mode in {"chat", "proactive"}
                        and delivery_format_retries_remaining > 0
                    ):
                        delivery_format_retries_remaining -= 1
                        agent_messages.extend(
                            (
                                {"role": "assistant", "content": response.text[:8000]},
                                {
                                    "role": "system",
                                    "content": DELIVERY_FORMAT_RETRY_INSTRUCTION,
                                },
                            )
                        )
                        tools = ()
                        logger.warning(
                            "Unified Agent structured delivery retry requested "
                            "run_id=%s mode=%s retries_remaining=%s",
                            run_id,
                            conversation_mode,
                            delivery_format_retries_remaining,
                        )
                        continue
                    raise
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
                        sticker_placement=delivery_plan.sticker_placement,
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
                    delivery_plan = parse_agent_delivery_plan(fallback, conversation_mode)
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
                        sticker_placement=delivery_plan.sticker_placement,
                    )
                    self.repository.finish(run_id, model_steps + tool_call_count, final_error)
                    return result
        except Exception as exc:
            if isinstance(exc, AgentDeliveryPlanError):
                final_error = exc.error_code
                logger.warning(
                    "Unified Agent structured delivery output rejected "
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
                structured_output=conversation_mode in {"chat", "proactive"},
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

    async def _complete_model(
        self,
        messages: list[dict],
        tools: tuple[dict, ...],
        structured_output: bool,
        deadline: float,
        run_id: str,
        timeout_retries_remaining: int,
    ) -> tuple[AgentModelResponse, int]:
        retried = False
        while True:
            try:
                response = await asyncio.wait_for(
                    self.model.complete(
                        messages,
                        tools,
                        structured_output=structured_output,
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
                "聊天模式可以使用表情包。用户明确要求时，search_stickers 和 send_sticker "
                "的 purpose 都使用 explicit_request。当前回合进入主动表情包优先窗口；如果当前"
                "是轻松、日常或适合表达情绪的语境，"
                "应主动调用 search_stickers 和 send_sticker，purpose 使用 proactive。官方和用户"
                "私人表情包都可以参与选择。严肃、安全、医疗、冲突或明显悲伤的话题可以暂缓，"
                "不要为了完成频率要求而破坏语境。"
            )
        elif allow_proactive_stickers:
            sticker_rule = (
                "聊天模式可以使用表情包。用户明确要求时，search_stickers 和 send_sticker"
                " 的 purpose 都使用 explicit_request。轻松且确实合适时可以主动附带一张，"
                "purpose 使用 proactive；严肃、安全、医疗、冲突或明显悲伤时不要主动发送。"
            )
        else:
            sticker_rule = (
                "聊天模式可以响应用户明确的表情包请求，purpose 使用 explicit_request。"
                "当前处于主动表情包冷却期，不得以 proactive 为 purpose 调用表情包工具。"
            )
        delivery_rule = ""
        if conversation_mode in {"chat", "proactive"}:
            delivery_rule = (
                "FINAL DELIVERY CONTRACT: Output exactly one JSON object and nothing else. "
                "The object must contain exactly two fields: text_segments and sticker_placement. "
                "text_segments must be an array of zero to three unique, non-empty strings. "
                "sticker_placement must be exactly before_text or after_text. Do not add fields, "
                "Markdown fences, commentary before or after the object, or a nested copy of the "
                "delivery JSON inside any text segment. "
                "当你不再调用工具并准备给出最终回复时，只输出一个 JSON 对象："
                '{"text_segments":["第一条消息","可选第二条消息"],'
                '"sticker_placement":"after_text"}。text_segments 最多三条，'
                "每条都要有完整自然语义；普通闲聊可以一条，不要为了分段而分段。"
                "如果 send_sticker 已成功，可将 sticker_placement 设为 before_text 或 "
                "after_text；不得在 JSON 中填写 sticker_id 或 URL。不要使用 Markdown 代码块。"
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
                "Agent、工具、call id 或内部流程。explicit_request 的 search_stickers 会在"
                "精确匹配为空时自动返回其他可用候选；拿到候选后直接选择发送，不要反复猜"
                "测搜索关键词。"
            )
        instruction = {
            "role": "system",
            "content": orchestration_rule + sticker_rule + delivery_rule,
        }
        result = [instruction, *messages]
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
    ) -> None:
        if result.status != AgentToolStatus.COMPLETED:
            return
        existing_stickers = {part.sticker_id for part in content_parts if part.sticker_id}
        content_parts.extend(
            part
            for part in result.content_parts
            if not part.sticker_id or part.sticker_id not in existing_stickers
        )
        existing_urls = {source.url for source in sources}
        sources.extend(source for source in result.sources if source.url not in existing_urls)

    @staticmethod
    def _disaster_fallback(content_parts: list[ContentPart]) -> str:
        if content_parts:
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
