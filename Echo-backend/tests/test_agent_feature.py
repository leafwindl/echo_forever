import asyncio
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.entities import (
    AgentModelResponse,
    AgentRunStatus,
    AgentToolCall,
    AgentToolStatus,
)
from features.agent.domain.services import AgentModelTimeoutError, resolve_local_time
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.infrastructure.model import ProviderAgentConversationModel
from features.agent.infrastructure.tools import (
    register_sticker_tools,
    register_time_tool,
    register_web_search_tool,
)
from features.stickers.domain.entities import Sticker
from providers.llm_provider import LLMProviderTimeoutError, OpenAICompatibleLLMProvider
from providers.web_search_provider import WebSearchItem, WebSearchResult


class FakeClock:
    def now(self):
        return datetime(2026, 7, 29, 8, 0, tzinfo=UTC)


class SequenceAgentModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, tools, *, structured_output=False):
        self.calls.append(
            {
                "messages": list(messages),
                "tools": tuple(tools),
                "structured_output": structured_output,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeAgentRunRepository:
    def __init__(self):
        self.tool_calls = []
        self.finishes = []

    def start(self, user_id, objective, trigger_type, max_steps):
        self.started = (user_id, objective, trigger_type, max_steps)
        return "run_test"

    def record_tool_call(
        self,
        run_id,
        tool_name,
        arguments,
        output,
        error_code=None,
        status=None,
        tool_call_id=None,
    ):
        self.tool_calls.append(
            {
                "run_id": run_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "output": output,
                "error_code": error_code,
                "status": status,
                "tool_call_id": tool_call_id,
            }
        )

    def finish(self, run_id, step_count, error_code=None):
        self.finishes.append((run_id, step_count, error_code))


class FakeWebSearch:
    def __init__(self, results=()):
        self.results = tuple(results)
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return WebSearchResult(
            results=self.results,
            retrieved_at="2026-08-05T12:00:00+00:00",
        )


def _sticker(sticker_id="stk_happy"):
    return Sticker(
        sticker_id=sticker_id,
        owner_type="echo",
        source="uploaded",
        url="https://example.test/happy.png",
        content_type="image/png",
        description="一只小狗在笑",
        semantic_tags=("开心",),
        status="active",
        created_at=datetime.now(UTC),
    )


def _tool_names(descriptions):
    return [item["function"]["name"] for item in descriptions]


def _delivery(*segments, placement="after_text"):
    return json.dumps(
        {
            "text_segments": list(segments),
            "sticker_placement": placement,
        },
        ensure_ascii=False,
    )


def _build_orchestrator(
    model,
    search=lambda _user_id, _query, _limit: [],
    send=lambda _user_id, _sticker_id: None,
    web_search=None,
    max_steps=6,
    max_tool_calls=4,
    run_timeout_seconds=45,
):
    repository = FakeAgentRunRepository()
    registry = ToolRegistry()
    register_sticker_tools(registry, search=search, send=send)
    register_time_tool(registry, FakeClock(), "Asia/Shanghai")
    register_web_search_tool(registry, web_search or FakeWebSearch())
    return (
        OrchestrateChatWithAgent(
            repository=repository,
            model=model,
            registry=registry,
            executor=ToolExecutor(registry),
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            run_timeout_seconds=run_timeout_seconds,
        ),
        repository,
        registry,
    )


class AgentDomainTests(unittest.TestCase):
    def test_time_tool_uses_iana_timezone(self):
        result = resolve_local_time(FakeClock(), "Asia/Shanghai")
        self.assertEqual(result["local_datetime"], "2026-07-29T16:00:00+08:00")
        self.assertEqual(result["timezone"], "Asia/Shanghai")

    def test_tool_registry_hides_sticker_tools_in_call_mode(self):
        _, _, registry = _build_orchestrator(SequenceAgentModel([AgentModelResponse(text="你好")]))

        self.assertIn("send_sticker", _tool_names(registry.model_descriptions("chat")))
        self.assertNotIn("send_sticker", _tool_names(registry.model_descriptions("call")))
        self.assertNotIn("search_stickers", _tool_names(registry.model_descriptions("call")))

    def test_due_turn_prioritizes_proactive_sticker_without_excluding_private_library(self):
        messages = OrchestrateChatWithAgent._build_initial_messages(
            messages=[{"role": "user", "content": "今天心情不错"}],
            conversation_mode="chat",
            sticker_intent="",
            allow_proactive_stickers=True,
            proactive_sticker_due=True,
        )

        instruction = messages[0]["content"]
        self.assertIn("主动表情包优先窗口", instruction)
        self.assertIn("官方和用户私人表情包都可以参与选择", instruction)


    def test_proactive_mode_forbids_assuming_current_user_activity(self):
        messages = OrchestrateChatWithAgent._build_initial_messages(
            messages=[{"role": "system", "content": "internal proactive trigger"}],
            conversation_mode="proactive",
            sticker_intent="",
            allow_proactive_stickers=True,
            proactive_sticker_due=False,
        )

        instruction = messages[0]["content"]
        self.assertIn("not by a new user message", instruction)
        self.assertIn("awake, online, reading", instruction)


class AgentProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_model_passes_configured_max_tokens_to_provider(self):
        class RecordingProvider:
            def __init__(self):
                self.kwargs = None

            async def chat_completion_message(self, **kwargs):
                self.kwargs = kwargs
                return type(
                    "Response",
                    (),
                    {
                        "content": "done",
                        "tool_calls": (),
                        "finish_reason": "stop",
                        "request_id": "req_test",
                    },
                )()

        provider = RecordingProvider()
        with patch(
            "features.agent.infrastructure.model.get_llm_provider",
            return_value=provider,
        ):
            await ProviderAgentConversationModel(max_tokens=2500).complete(
                messages=[{"role": "user", "content": "写信"}],
                tools=(),
                structured_output=True,
            )

        self.assertEqual(provider.kwargs["max_tokens"], 2500)
        self.assertEqual(provider.kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(provider.kwargs["thinking"], {"type": "disabled"})

    async def test_provider_sends_native_json_response_format(self):
        class RecordingResponse:
            headers = {}

            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {
                    "id": "req_json",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    '{"text_segments":["你好"],'
                                    '"sticker_placement":"after_text"}'
                                )
                            },
                        }
                    ],
                }

        class RecordingClient:
            def __init__(self):
                self.payload = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                del exc_type, exc, traceback

            async def post(self, url, headers, json):
                del url, headers
                self.payload = json
                return RecordingResponse()

        client = RecordingClient()
        with patch(
            "providers.llm_provider.httpx.AsyncClient",
            return_value=client,
        ):
            await OpenAICompatibleLLMProvider().chat_completion_message(
                messages=[{"role": "user", "content": "你好"}],
                response_format={"type": "json_object"},
                thinking={"type": "disabled"},
            )

        self.assertEqual(client.payload["response_format"], {"type": "json_object"})
        self.assertEqual(client.payload["thinking"], {"type": "disabled"})

    async def test_http_timeout_is_preserved_as_provider_timeout(self):
        class TimeoutClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                del exc_type, exc, traceback

            async def post(self, url, headers, json):
                del headers, json
                raise httpx.ReadTimeout("provider timeout", request=httpx.Request("POST", url))

        with (
            patch(
                "providers.llm_provider.httpx.AsyncClient",
                return_value=TimeoutClient(),
            ),
            self.assertRaises(LLMProviderTimeoutError),
        ):
            await OpenAICompatibleLLMProvider().chat_completion_message(
                messages=[{"role": "user", "content": "你好"}],
            )

    async def test_provider_timeout_is_mapped_to_agent_model_timeout(self):
        class TimeoutProvider:
            async def chat_completion_message(self, **kwargs):
                del kwargs
                raise LLMProviderTimeoutError("provider timeout")

        with (
            patch(
                "features.agent.infrastructure.model.get_llm_provider",
                return_value=TimeoutProvider(),
            ),
            self.assertRaises(AgentModelTimeoutError),
        ):
            await ProviderAgentConversationModel().complete(
                messages=[{"role": "user", "content": "你好"}],
                tools=(),
            )


class AgentOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_letter_truncation_fails_without_repeating_empty_calls(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    text="",
                    finish_reason="length",
                    provider_request_id="req_truncated",
                )
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model, max_steps=2)

        result = await orchestrator.execute(
            user_id="user_a",
            message="Generate daily letter",
            messages=[{"role": "user", "content": "写信"}],
            conversation_mode="daily_letter",
            tools_enabled=False,
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.error_code, "llm_output_truncated")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0], ("run_test", 1, "llm_output_truncated"))

    async def test_normal_chat_and_tools_share_one_agent_runtime(self):
        model = SequenceAgentModel(
            [AgentModelResponse(text=_delivery("今天听起来心情不错。"))]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="今天心情不错",
            messages=[{"role": "user", "content": "今天心情不错"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "今天听起来心情不错。")
        self.assertEqual(result.content_parts, ())
        self.assertIn("get_current_time", _tool_names(model.calls[0]["tools"]))
        self.assertEqual(repository.tool_calls, [])
        self.assertEqual(repository.finishes[0][2], None)

    async def test_agent_searches_sends_and_naturally_finishes_sticker_turn(self):
        sticker = _sticker()
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_search",
                            tool_name="search_stickers",
                            arguments={
                                "query": "开心",
                                "limit": 1,
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "sticker_id": sticker.sticker_id,
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("这个笑得很有感染力，给你。")),
            ]
        )
        searches = []
        sends = []

        def search(user_id, query, limit):
            searches.append((user_id, query, limit))
            return [sticker]

        def send(user_id, sticker_id):
            sends.append((user_id, sticker_id))
            return sticker

        orchestrator, repository, _ = _build_orchestrator(model, search=search, send=send)

        result = await orchestrator.execute(
            user_id="user_a",
            message="给我发一个开心的表情包",
            messages=[
                {"role": "assistant", "content": "我没有发送图片的能力。"},
                {"role": "user", "content": "给我发一个开心的表情包"},
            ],
        )

        self.assertEqual(result.reply_text, "这个笑得很有感染力，给你。")
        self.assertEqual(result.content_parts[0].sticker_id, sticker.sticker_id)
        self.assertEqual(searches, [("user_a", "开心", 1)])
        self.assertEqual(sends, [("user_a", sticker.sticker_id)])
        self.assertEqual(
            [call["status"] for call in repository.tool_calls],
            ["completed", "completed"],
        )
        final_messages = model.calls[-1]["messages"]
        self.assertEqual(final_messages[-1]["role"], "tool")
        self.assertIn("attached_to_current_reply", final_messages[-1]["content"])
        self.assertIn("关于能力的说法可能过时", model.calls[0]["messages"][0]["content"])

    async def test_search_no_result_returns_to_same_model_for_natural_reply(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_search",
                            tool_name="search_stickers",
                            arguments={
                                "query": "困惑",
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("这次没找到语义合适的，我先不乱发。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="发个困惑的表情包",
            messages=[{"role": "user", "content": "发个困惑的表情包"}],
        )

        self.assertEqual(result.reply_text, "这次没找到语义合适的，我先不乱发。")
        self.assertEqual(result.content_parts, ())
        self.assertEqual(repository.tool_calls[0]["status"], "no_result")

    async def test_search_no_result_does_not_consume_search_call_limit(self):
        registry = ToolRegistry()
        register_sticker_tools(
            registry,
            search=lambda _user_id, _query, _limit: [],
        )
        executor = ToolExecutor(registry)
        prior_results = []

        for index in range(3):
            result = await executor.execute(
                ToolExecutionContext(
                    user_id="user_a",
                    prior_results=tuple(prior_results),
                ),
                AgentToolCall(
                    call_id=f"search_{index}",
                    tool_name="search_stickers",
                    arguments={
                        "query": f"intent_{index}",
                        "purpose": "proactive",
                    },
                ),
            )
            prior_results.append(result)

        self.assertEqual(
            [result.status for result in prior_results],
            [AgentToolStatus.NO_RESULT] * 3,
        )
        self.assertNotIn(
            "tool_call_limit",
            [result.error_code for result in prior_results],
        )

    async def test_explicit_sticker_search_falls_back_to_any_available_sticker(self):
        sticker = _sticker()
        searches = []
        sends = []

        def search(user_id, query, limit):
            searches.append((user_id, query, limit))
            return [sticker] if not query else []

        def send(user_id, sticker_id):
            sends.append((user_id, sticker_id))
            return sticker

        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_search",
                            tool_name="search_stickers",
                            arguments={
                                "query": "困惑",
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "sticker_id": sticker.sticker_id,
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("没找到完全对应的，这张先陪你。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(
            model,
            search=search,
            send=send,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="随便发一张表情包",
            messages=[{"role": "user", "content": "随便发一张表情包"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.content_parts[0].sticker_id, sticker.sticker_id)
        self.assertEqual(searches, [("user_a", "困惑", 3), ("user_a", "", 3)])
        self.assertTrue(repository.tool_calls[0]["output"]["fallback_used"])
        self.assertEqual(sends, [("user_a", sticker.sticker_id)])

    async def test_call_mode_rejects_sticker_tool_even_if_model_hallucinates_it(self):
        sent = []
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_bad",
                            tool_name="send_sticker",
                            arguments={
                                "sticker_id": "stk_bad",
                                "purpose": "explicit_request",
                            },
                        ),
                    )
                ),
                AgentModelResponse(text="通话里先继续说话，图片不会发送。"),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(
            model,
            send=lambda _user_id, sticker_id: sent.append(sticker_id),
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="发个表情包",
            messages=[{"role": "user", "content": "发个表情包"}],
            conversation_mode="call",
        )

        self.assertNotIn("send_sticker", _tool_names(model.calls[0]["tools"]))
        self.assertEqual(result.content_parts, ())
        self.assertEqual(sent, [])
        self.assertEqual(repository.tool_calls[0]["error_code"], "tool_not_allowed_in_mode")

    async def test_proactive_sticker_is_blocked_during_cooldown(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_search",
                            tool_name="search_stickers",
                            arguments={"query": "开心", "purpose": "proactive"},
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("这次先陪你聊，不刷图。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="今天还不错",
            messages=[{"role": "user", "content": "今天还不错"}],
            allow_proactive_stickers=False,
        )

        self.assertEqual(result.content_parts, ())
        self.assertEqual(repository.tool_calls[0]["error_code"], "proactive_sticker_cooldown")

    async def test_send_tool_rejects_sticker_not_returned_by_search(self):
        allowed = _sticker("stk_allowed")
        sent = []
        registry = ToolRegistry()
        register_sticker_tools(
            registry,
            search=lambda _user_id, _query, _limit: [allowed],
            send=lambda _user_id, sticker_id: sent.append(sticker_id) or allowed,
        )
        executor = ToolExecutor(registry)

        result = await executor.execute(
            ToolExecutionContext(user_id="user_a"),
            AgentToolCall(
                call_id="tool_test",
                tool_name="send_sticker",
                arguments={
                    "sticker_id": "stk_untrusted",
                    "purpose": "explicit_request",
                },
            ),
        )

        self.assertEqual(result.status, AgentToolStatus.FAILED)
        self.assertEqual(result.error_code, "sticker_not_in_search_results")
        self.assertEqual(sent, [])

    async def test_failed_send_can_retry_after_search_changes_candidates(self):
        sticker = _sticker()
        sent = []
        registry = ToolRegistry()
        register_sticker_tools(
            registry,
            search=lambda _user_id, _query, _limit: [sticker],
            send=lambda _user_id, sticker_id: sent.append(sticker_id) or sticker,
        )
        executor = ToolExecutor(registry)
        send_arguments = {
            "sticker_id": sticker.sticker_id,
            "purpose": "explicit_request",
        }

        failed_send = await executor.execute(
            ToolExecutionContext(user_id="user_a"),
            AgentToolCall(
                call_id="send_before_search",
                tool_name="send_sticker",
                arguments=send_arguments,
            ),
        )
        search_result = await executor.execute(
            ToolExecutionContext(user_id="user_a", prior_results=(failed_send,)),
            AgentToolCall(
                call_id="search_after_failure",
                tool_name="search_stickers",
                arguments={
                    "query": "开心",
                    "purpose": "explicit_request",
                },
            ),
        )
        retried_send = await executor.execute(
            ToolExecutionContext(
                user_id="user_a",
                prior_results=(failed_send, search_result),
            ),
            AgentToolCall(
                call_id="send_after_search",
                tool_name="send_sticker",
                arguments=send_arguments,
            ),
        )

        self.assertEqual(failed_send.error_code, "sticker_not_in_search_results")
        self.assertEqual(search_result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(retried_send.status, AgentToolStatus.COMPLETED)
        self.assertEqual(sent, [sticker.sticker_id])

    async def test_send_sticker_allows_only_one_success_per_turn(self):
        first_sticker = _sticker("stk_first")
        second_sticker = _sticker("stk_second")
        sent = []
        registry = ToolRegistry()
        register_sticker_tools(
            registry,
            search=lambda _user_id, _query, _limit: [first_sticker, second_sticker],
            send=lambda _user_id, sticker_id: (
                sent.append(sticker_id)
                or (first_sticker if sticker_id == first_sticker.sticker_id else second_sticker)
            ),
        )
        executor = ToolExecutor(registry)
        search_result = await executor.execute(
            ToolExecutionContext(user_id="user_a"),
            AgentToolCall(
                call_id="search_two",
                tool_name="search_stickers",
                arguments={"query": "开心", "purpose": "explicit_request"},
            ),
        )
        first_send = await executor.execute(
            ToolExecutionContext(user_id="user_a", prior_results=(search_result,)),
            AgentToolCall(
                call_id="send_first",
                tool_name="send_sticker",
                arguments={
                    "sticker_id": first_sticker.sticker_id,
                    "purpose": "explicit_request",
                },
            ),
        )
        second_send = await executor.execute(
            ToolExecutionContext(
                user_id="user_a",
                prior_results=(search_result, first_send),
            ),
            AgentToolCall(
                call_id="send_second",
                tool_name="send_sticker",
                arguments={
                    "sticker_id": second_sticker.sticker_id,
                    "purpose": "explicit_request",
                },
            ),
        )

        self.assertEqual(first_send.status, AgentToolStatus.COMPLETED)
        self.assertEqual(second_send.error_code, "tool_success_limit")
        self.assertEqual(sent, [first_sticker.sticker_id])

    async def test_executor_rejects_duplicate_tool_call(self):
        sticker = _sticker()
        searches = []
        registry = ToolRegistry()

        def search(user_id, query, limit):
            searches.append((user_id, query, limit))
            return [sticker]

        register_sticker_tools(
            registry,
            search=search,
            send=lambda _user_id, _sticker_id: sticker,
        )
        executor = ToolExecutor(registry)
        call = AgentToolCall(
            call_id="tool_first",
            tool_name="search_stickers",
            arguments={
                "query": "开心",
                "limit": 1,
                "purpose": "explicit_request",
            },
        )
        first = await executor.execute(ToolExecutionContext(user_id="user_a"), call)
        duplicate = await executor.execute(
            ToolExecutionContext(user_id="user_a", prior_results=(first,)),
            AgentToolCall(
                call_id="tool_second",
                tool_name="search_stickers",
                arguments=call.arguments,
            ),
        )

        self.assertEqual(first.status, AgentToolStatus.COMPLETED)
        self.assertEqual(duplicate.error_code, "duplicate_tool_call")
        self.assertEqual(searches, [("user_a", "开心", 1)])

    async def test_time_tool_result_is_returned_to_same_model(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_time",
                            tool_name="get_current_time",
                            arguments={"timezone": "Asia/Shanghai", "day_offset": 0},
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("现在是 2026 年 7 月 29 日 16:00。")),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="现在几点",
            messages=[{"role": "user", "content": "现在几点"}],
        )

        self.assertEqual(result.reply_text, "现在是 2026 年 7 月 29 日 16:00。")
        self.assertIn("2026-07-29T16:00:00+08:00", model.calls[-1]["messages"][-1]["content"])

    async def test_web_search_sources_are_authoritative_tool_output(self):
        web = FakeWebSearch(
            [
                WebSearchItem(
                    title="来源一",
                    canonical_url="https://example.test/source",
                    snippet="可靠摘要",
                )
            ]
        )
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_web",
                            tool_name="search_web",
                            arguments={"query": "最新消息", "limit": 1},
                        ),
                    )
                ),
                AgentModelResponse(text=_delivery("根据刚查到的来源，情况是这样。")),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(model, web_search=web)

        result = await orchestrator.execute(
            user_id="user_a",
            message="查一下最新消息",
            messages=[{"role": "user", "content": "查一下最新消息"}],
        )

        self.assertEqual(result.sources[0].url, "https://example.test/source")
        self.assertEqual(web.requests[0].query, "最新消息")

    async def test_model_failure_never_uses_a_separate_reply_model(self):
        model = SequenceAgentModel([ValueError("model unavailable")])
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="你好",
            messages=[{"role": "user", "content": "你好"}],
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.reply_text, "刚才这次回复没有完成，再和我说一次好吗？")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0][2], "ValueError")

    async def test_proactive_model_failure_is_not_delivered_as_a_user_retry(self):
        model = SequenceAgentModel([ValueError("model unavailable")])
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="A proactive message is due.",
            messages=[{"role": "user", "content": "A proactive message is due."}],
            conversation_mode="proactive",
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.reply_text, "")
        self.assertEqual(result.reply_segments, ())
        self.assertEqual(result.content_parts, ())
        self.assertEqual(result.error_code, "ValueError")
        self.assertEqual(repository.finishes[0][2], "ValueError")

    async def test_proactive_truncated_empty_output_retries_then_stays_silent(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(text="", finish_reason="length"),
                AgentModelResponse(text="", finish_reason="length"),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="A proactive message is due.",
            messages=[{"role": "user", "content": "A proactive message is due."}],
            conversation_mode="proactive",
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.reply_text, "")
        self.assertEqual(result.reply_segments, ())
        self.assertEqual(result.error_code, "llm_output_truncated")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertEqual(repository.finishes[0][2], "llm_output_truncated")

    async def test_chat_truncated_empty_output_retries_and_recovers(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    text="",
                    finish_reason="length",
                    provider_request_id="req_empty",
                ),
                AgentModelResponse(text=_delivery("这次正常回复了。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="你好",
            messages=[{"role": "user", "content": "你好"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "这次正常回复了。")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertEqual(repository.finishes[0][2], None)

    async def test_malformed_structured_output_is_failed_without_protocol_fragment(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(text='{"text_segments'),
                AgentModelResponse(text='{"text_segments'),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="hello",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.error_code, "llm_output_malformed")
        self.assertNotIn("text_segments", result.reply_text)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertEqual(repository.finishes[0][2], "llm_output_malformed")

    async def test_malformed_structured_output_is_repaired_once_without_tools(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    text=(
                        'hello {"text_segments":["hello"],'
                        '"sticker_placement":"after_text"}'
                    )
                ),
                AgentModelResponse(text=_delivery("hello")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="hello",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "hello")
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(model.calls[0]["structured_output"])
        self.assertTrue(model.calls[1]["structured_output"])
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertIn("FINAL DELIVERY CONTRACT", model.calls[0]["messages"][0]["content"])
        self.assertEqual(repository.finishes[0][2], None)

    async def test_structured_retry_does_not_echo_invalid_output_or_internal_time_markers(self):
        leaked_output = "[消息时间 2026-08-13T09:12:35+08:00 周四 上午]\n我也想再睡会儿。"
        model = SequenceAgentModel(
            [
                AgentModelResponse(text=leaked_output),
                AgentModelResponse(text=_delivery("那就再眯一会儿。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="我还想再睡一会儿",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "[会话时间边界] 上一段消息结束于昨晚，本段开始于今早。"
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        "[消息时间 2026-08-13T09:00:00+08:00 周四 上午]\n早上好。"
                    ),
                },
                {"role": "user", "content": "我还想再睡一会儿"},
            ],
        )

        retry_messages = model.calls[1]["messages"]
        retry_contents = [str(message.get("content") or "") for message in retry_messages]
        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "那就再眯一会儿。")
        self.assertNotIn(leaked_output, retry_contents)
        self.assertFalse(any("[消息时间" in content for content in retry_contents))
        self.assertFalse(any("[会话时间边界" in content for content in retry_contents))
        self.assertIn("早上好。", retry_contents)
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertEqual(repository.finishes[0][2], None)

    async def test_proactive_malformed_structured_output_is_silent(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(text='{"text_segments'),
                AgentModelResponse(text='{"text_segments'),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="A proactive message is due.",
            messages=[{"role": "system", "content": "internal proactive trigger"}],
            conversation_mode="proactive",
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.reply_text, "")
        self.assertEqual(result.reply_segments, ())
        self.assertEqual(result.content_parts, ())
        self.assertEqual(result.error_code, "llm_output_malformed")
        self.assertEqual(repository.finishes[0][2], "llm_output_malformed")

    async def test_llm_timeout_is_retried_once_and_can_recover(self):
        model = SequenceAgentModel(
            [
                AgentModelTimeoutError("provider timed out"),
                AgentModelResponse(text=_delivery("刚才慢了一下，现在好了。")),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="你好",
            messages=[{"role": "user", "content": "你好"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "刚才慢了一下，现在好了。")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(repository.finishes[0][2], None)

    async def test_llm_timeout_is_recorded_after_one_retry(self):
        model = SequenceAgentModel(
            [
                AgentModelTimeoutError("first timeout"),
                AgentModelTimeoutError("second timeout"),
            ]
        )
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="你好",
            messages=[{"role": "user", "content": "你好"}],
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.error_code, "llm_timeout")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(repository.finishes[0][2], "llm_timeout")

    async def test_agent_timeout_never_executes_side_effect_tool(self):
        class SlowModel:
            async def complete(self, messages, tools, *, structured_output=False):
                del messages, tools, structured_output
                await asyncio.sleep(0.05)
                return AgentModelResponse(text="不会到这里")

        sent = []
        orchestrator, repository, _ = _build_orchestrator(
            SlowModel(),
            send=lambda _user_id, sticker_id: sent.append(sticker_id),
            run_timeout_seconds=0.01,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="来一张开心的",
            messages=[{"role": "user", "content": "来一张开心的"}],
        )

        self.assertEqual(result.status, AgentRunStatus.FAILED)
        self.assertEqual(result.error_code, "agent_timeout")
        self.assertEqual(sent, [])
        self.assertEqual(repository.finishes[0][2], "agent_timeout")


if __name__ == "__main__":
    unittest.main()
