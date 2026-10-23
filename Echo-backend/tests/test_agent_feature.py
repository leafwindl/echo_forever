import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.call_routing import CallToolMode, route_call_tools
from features.agent.domain.entities import (
    AgentModelResponse,
    AgentRunStatus,
    AgentToolCall,
    AgentToolResult,
    AgentToolStatus,
)
from features.agent.domain.services import (
    AgentModelTimeoutError,
    StickerRequestDecision,
    StickerToolPolicy,
    resolve_local_time,
)
from features.agent.domain.tools import ToolExecutionContext, ToolRegistry
from features.agent.infrastructure.container import get_chat_agent
from features.agent.infrastructure.model import ProviderAgentConversationModel
from features.agent.infrastructure.sticker_semantics import ProviderStickerSemanticAnalyzer
from features.agent.infrastructure.tools import (
    register_schedule_tools,
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

    async def complete(
        self,
        messages,
        tools,
        *,
        structured_output=False,
        tool_choice="auto",
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "tools": tuple(tools),
                "structured_output": structured_output,
                "tool_choice": tool_choice,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeStickerSemanticAnalyzer:
    def __init__(self, *, decision=None, claims=()):
        self.decision = decision or StickerRequestDecision(StickerToolPolicy.OPTIONAL)
        self.claims = list(claims)
        self.request_calls = []
        self.claim_calls = []

    async def assess_request(self, message, messages):
        self.request_calls.append((message, list(messages)))
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision

    async def claims_sticker_delivery(self, reply_text):
        self.claim_calls.append(reply_text)
        if not self.claims:
            return False
        result = self.claims.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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
    del placement
    return "\n\n".join(segments)


def _build_orchestrator(
    model,
    search=lambda _user_id, _query, _limit: [],
    send=lambda _user_id, _sticker_id: None,
    web_search=None,
    max_steps=6,
    max_tool_calls=4,
    run_timeout_seconds=45,
    sticker_semantic_analyzer=None,
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
            sticker_semantic_analyzer=sticker_semantic_analyzer,
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

    def test_call_router_keeps_normal_dialogue_on_fast_path(self):
        route = route_call_tools(
            "今天有点累，陪我聊会儿",
            web_search_available=True,
            schedule_tools_available=True,
        )

        self.assertEqual(route.mode, CallToolMode.FAST_CHAT)
        self.assertEqual(route.allowed_tool_names, ())

    def test_call_router_exposes_only_requested_search_capability(self):
        route = route_call_tools(
            "帮我查一下今天有什么新闻",
            web_search_available=True,
            schedule_tools_available=True,
        )

        self.assertEqual(route.mode, CallToolMode.WEB_SEARCH)
        self.assertEqual(route.allowed_tool_names, ("search_web",))
        self.assertEqual(route.maximum_tool_calls, 1)

    def test_call_router_never_pretends_disabled_search_is_available(self):
        route = route_call_tools(
            "搜索一下最新消息",
            web_search_available=False,
            schedule_tools_available=True,
        )

        self.assertEqual(route.mode, CallToolMode.WEB_SEARCH)
        self.assertEqual(route.allowed_tool_names, ())
        self.assertIn("不要用模型内部知识冒充搜索结果", route.instruction)

    def test_call_router_only_exposes_schedule_list_on_the_first_manage_step(self):
        route = route_call_tools(
            "取消我明天的提醒",
            web_search_available=True,
            schedule_tools_available=True,
        )

        self.assertEqual(route.mode, CallToolMode.SCHEDULE_MANAGE)
        self.assertEqual(route.allowed_tool_names, ("list_chat_schedules",))
        self.assertEqual(route.maximum_tool_calls, 2)

    def test_tool_registry_filters_call_tools_by_route(self):
        _, _, registry = _build_orchestrator(
            SequenceAgentModel([AgentModelResponse(text="你好")])
        )

        descriptions = registry.model_descriptions("call", ("search_web",))

        self.assertEqual(_tool_names(descriptions), ["search_web"])

    def test_sticker_policy_has_no_elapsed_turn_quota(self):
        messages = OrchestrateChatWithAgent._build_initial_messages(
            messages=[{"role": "user", "content": "今天心情不错"}],
            conversation_mode="chat",
            sticker_intent="",
            allow_proactive_stickers=True,
        )

        instruction = messages[0]["content"]
        self.assertNotIn("主动表情包优先窗口", instruction)
        self.assertIn("没有轮数配额", instruction)
        self.assertIn("官方和用户私人表情包都可以参与选择", instruction)


    def test_proactive_mode_forbids_assuming_current_user_activity(self):
        messages = OrchestrateChatWithAgent._build_initial_messages(
            messages=[{"role": "system", "content": "internal proactive trigger"}],
            conversation_mode="proactive",
            sticker_intent="",
            allow_proactive_stickers=True,
        )

        instruction = messages[0]["content"]
        self.assertIn("并非用户发来新消息", instruction)
        self.assertIn("不能据此推断用户醒着、在线、正在读消息", instruction)


class AgentProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_agent_model_disables_thinking_and_uses_its_token_budget(self):
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
            await ProviderAgentConversationModel(
                max_tokens=1000,
                temperature=0.1,
                disable_thinking=True,
            ).complete(
                messages=[{"role": "user", "content": "你好"}],
                tools=(),
            )

        self.assertEqual(provider.kwargs["max_tokens"], 1000)
        self.assertEqual(provider.kwargs["temperature"], 0.1)
        self.assertIsNone(provider.kwargs["response_format"])
        self.assertEqual(provider.kwargs["thinking"], {"type": "disabled"})

    async def test_agent_model_forwards_a_named_native_tool_choice(self):
        class RecordingProvider:
            def __init__(self):
                self.kwargs = None

            async def chat_completion_message(self, **kwargs):
                self.kwargs = kwargs
                return type(
                    "Response",
                    (),
                    {
                        "content": "",
                        "tool_calls": (),
                        "finish_reason": "tool_calls",
                        "request_id": "req_tool_choice",
                    },
                )()

        provider = RecordingProvider()
        tool_choice = {
            "type": "function",
            "function": {"name": "send_sticker"},
        }
        with patch(
            "features.agent.infrastructure.model.get_llm_provider",
            return_value=provider,
        ):
            await ProviderAgentConversationModel().complete(
                messages=[{"role": "user", "content": "发一个表情包"}],
                tools=(),
                tool_choice=tool_choice,
            )

        self.assertEqual(provider.kwargs["tool_choice"], tool_choice)

    async def test_structured_agent_output_still_disables_thinking(self):
        class RecordingProvider:
            def __init__(self):
                self.kwargs = None

            async def chat_completion_message(self, **kwargs):
                self.kwargs = kwargs
                return type(
                    "Response",
                    (),
                    {
                        "content": "{}",
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

    def test_chat_agent_container_uses_dedicated_budget_and_disables_thinking(self):
        get_chat_agent.cache_clear()
        try:
            agent = get_chat_agent()
            self.assertEqual(agent.model.max_tokens, 1000)
            self.assertTrue(agent.model.disable_thinking)
        finally:
            get_chat_agent.cache_clear()

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

    async def test_provider_streams_text_deltas_and_reassembles_tool_calls(self):
        class StreamingResponse:
            headers = {"x-request-id": "req_stream"}
            status_code = 200

            def raise_for_status(self):
                return None

            async def aiter_lines(self):
                yield (
                    'data: {"id":"req_stream","choices":'
                    '[{"delta":{"content":"你好"},"finish_reason":null}]}'
                )
                yield 'data: {"choices":[{"delta":{"content":"，Echo"},"finish_reason":null}]}'
                yield (
                    'data: {"choices":[{"delta":{"tool_calls":'
                    '[{"index":0,"id":"call_1","function":{"name":"get_time",'
                    '"arguments":"{\\"zone\\":\\"Asia/Shanghai\\"}"}}]},'
                    '"finish_reason":"tool_calls"}]}'
                )
                yield "data: [DONE]"

        class StreamContext:
            async def __aenter__(self):
                return StreamingResponse()

            async def __aexit__(self, exc_type, exc, traceback):
                del exc_type, exc, traceback

        class StreamingClient:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                del exc_type, exc, traceback

            def stream(self, *_args, **_kwargs):
                return StreamContext()

        deltas = []

        async def record_delta(text):
            deltas.append(text)

        with patch("providers.llm_provider.httpx.AsyncClient", StreamingClient):
            result = await OpenAICompatibleLLMProvider().stream_chat_completion_message(
                messages=[{"role": "user", "content": "你好"}],
                on_text_delta=record_delta,
            )

        self.assertEqual(deltas, ["你好", "，Echo"])
        self.assertEqual(result.content, "你好，Echo")
        self.assertEqual(result.request_id, "req_stream")
        self.assertEqual(result.tool_calls[0].name, "get_time")
        self.assertEqual(result.tool_calls[0].arguments["zone"], "Asia/Shanghai")

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


class StickerSemanticAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_analysis_uses_forced_function_call_and_validates_arguments(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="invalid",
                            tool_name="classify_sticker_request",
                            arguments={"policy": "required", "intent": "", "extra": True},
                        ),
                    )
                ),
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="valid",
                            tool_name="classify_sticker_request",
                            arguments={"policy": "required", "intent": "晚安休息"},
                        ),
                    )
                ),
            ]
        )
        analyzer = ProviderStickerSemanticAnalyzer(model)

        decision = await analyzer.assess_request(
            "那给我来一张吧",
            [
                {"role": "user", "content": "我准备睡觉了"},
                {"role": "assistant", "content": "要不要一张晚安表情包？"},
            ],
        )

        self.assertEqual(decision.policy, StickerToolPolicy.REQUIRED)
        self.assertEqual(decision.intent, "晚安休息")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(
            model.calls[0]["tool_choice"],
            {
                "type": "function",
                "function": {"name": "classify_sticker_request"},
            },
        )

    async def test_delivery_claim_analysis_uses_boolean_function_result(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="claim",
                            tool_name="classify_sticker_delivery_claim",
                            arguments={"claims_delivery": True},
                        ),
                    )
                )
            ]
        )

        claimed = await ProviderStickerSemanticAnalyzer(model).claims_sticker_delivery(
            "这张给你，今晚好好休息。"
        )

        self.assertTrue(claimed)


class AgentOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def test_completed_schedule_side_effect_has_deterministic_confirmation(self):
        created = AgentToolResult(
            call_id="schedule",
            tool_name="create_chat_schedule",
            status=AgentToolStatus.COMPLETED,
            data={"created": True, "label": "十一点半叫我"},
        )
        cancelled = AgentToolResult(
            call_id="cancel",
            tool_name="cancel_chat_schedule",
            status=AgentToolStatus.COMPLETED,
            data={"cancelled": True},
        )

        self.assertEqual(
            OrchestrateChatWithAgent._deterministic_tool_confirmation([created]),
            "好，已经帮你设置好了：十一点半叫我。",
        )
        self.assertEqual(
            OrchestrateChatWithAgent._deterministic_tool_confirmation([cancelled]),
            "好，这个提醒已经取消了。",
        )

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

    async def test_required_sticker_request_forces_high_level_send_and_finishes(self):
        sticker = _sticker()
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "intent": "开心有感染力",
                                "purpose": "explicit_request",
                                "placement": "before_text",
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

        semantic_analyzer = FakeStickerSemanticAnalyzer(
            decision=StickerRequestDecision(
                StickerToolPolicy.REQUIRED,
                "开心有感染力",
            )
        )
        orchestrator, repository, _ = _build_orchestrator(
            model,
            search=search,
            send=send,
            sticker_semantic_analyzer=semantic_analyzer,
        )

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
        self.assertEqual(result.sticker_placement, "before_text")
        self.assertEqual(searches, [("user_a", "开心有感染力", 3)])
        self.assertEqual(sends, [("user_a", sticker.sticker_id)])
        self.assertEqual([call["status"] for call in repository.tool_calls], ["completed"])
        self.assertEqual(
            model.calls[0]["tool_choice"],
            {"type": "function", "function": {"name": "send_sticker"}},
        )
        final_messages = model.calls[-1]["messages"]
        self.assertEqual(final_messages[-1]["role"], "tool")
        self.assertIn("attached_to_current_reply", final_messages[-1]["content"])
        self.assertIn("关于能力的说法可能过时", model.calls[0]["messages"][0]["content"])

    async def test_required_sticker_request_retries_when_model_omits_tool_call(self):
        sticker = _sticker()
        model = SequenceAgentModel(
            [
                AgentModelResponse(text="我直接说就好。"),
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "intent": "晚安休息",
                                "purpose": "proactive",
                            },
                        ),
                    )
                ),
                AgentModelResponse(text="晚安，早点休息。"),
            ]
        )
        analyzer = FakeStickerSemanticAnalyzer(
            decision=StickerRequestDecision(
                StickerToolPolicy.REQUIRED,
                "晚安休息",
            )
        )
        orchestrator, repository, _ = _build_orchestrator(
            model,
            search=lambda _user_id, _query, _limit: [sticker],
            send=lambda _user_id, _sticker_id: sticker,
            sticker_semantic_analyzer=analyzer,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="给我来个晚安表情包",
            messages=[{"role": "user", "content": "给我来个晚安表情包"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.content_parts[0].sticker_id, sticker.sticker_id)
        self.assertEqual(repository.tool_calls[0]["arguments"]["purpose"], "explicit_request")
        self.assertEqual(len(model.calls), 3)
        self.assertIn(
            "只调用 send_sticker",
            model.calls[1]["messages"][-1]["content"],
        )

    async def test_unbacked_sticker_claim_is_rewritten_once_before_delivery(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(text="（附上一张安静的表情包）今晚就慢一点。"),
                AgentModelResponse(text="今晚就慢一点，我陪你安静一会儿。"),
            ]
        )
        analyzer = FakeStickerSemanticAnalyzer(claims=(True, False))
        orchestrator, repository, _ = _build_orchestrator(
            model,
            sticker_semantic_analyzer=analyzer,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="今天有点累",
            messages=[{"role": "user", "content": "今天有点累"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "今晚就慢一点，我陪你安静一会儿。")
        self.assertEqual(result.content_parts, ())
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertIn("没有成功的发送凭证", model.calls[1]["messages"][-1]["content"])
        self.assertEqual(repository.tool_calls, [])

    async def test_repeated_unbacked_sticker_claim_uses_deterministic_safe_reply(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(text="这张给你。"),
                AgentModelResponse(text="再附上一张给你。"),
            ]
        )
        analyzer = FakeStickerSemanticAnalyzer(claims=(True, True))
        orchestrator, _, _ = _build_orchestrator(
            model,
            sticker_semantic_analyzer=analyzer,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="今天有点累",
            messages=[{"role": "user", "content": "今天有点累"}],
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "我在，继续和你说。")
        self.assertEqual(result.content_parts, ())

    async def test_high_level_send_no_result_returns_to_same_model(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "intent": "困惑",
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

    async def test_send_no_result_does_not_consume_tool_call_limit(self):
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
                    call_id=f"send_{index}",
                    tool_name="send_sticker",
                    arguments={
                        "intent": f"intent_{index}",
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

    async def test_explicit_send_falls_back_to_any_available_sticker(self):
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
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={
                                "intent": "困惑",
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
                                "intent": "开心",
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
                            call_id="call_send",
                            tool_name="send_sticker",
                            arguments={"intent": "开心", "purpose": "proactive"},
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

    async def test_send_tool_only_sends_top_ranked_search_result(self):
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
                    "intent": "开心",
                    "purpose": "explicit_request",
                },
            ),
        )

        self.assertEqual(result.status, AgentToolStatus.COMPLETED)
        self.assertEqual(result.data["sticker_id"], allowed.sticker_id)
        self.assertEqual(sent, [allowed.sticker_id])

    async def test_failed_send_can_retry_with_a_different_semantic_intent(self):
        sticker = _sticker()
        sent = []
        registry = ToolRegistry()
        register_sticker_tools(
            registry,
            search=lambda _user_id, _query, _limit: [sticker],
            send=lambda _user_id, sticker_id: (
                sent.append(sticker_id) or (None if len(sent) == 1 else sticker)
            ),
        )
        executor = ToolExecutor(registry)

        failed_send = await executor.execute(
            ToolExecutionContext(user_id="user_a"),
            AgentToolCall(
                call_id="send_first",
                tool_name="send_sticker",
                arguments={
                    "intent": "开心",
                    "purpose": "explicit_request",
                },
            ),
        )
        retried_send = await executor.execute(
            ToolExecutionContext(
                user_id="user_a",
                prior_results=(failed_send,),
            ),
            AgentToolCall(
                call_id="send_second",
                tool_name="send_sticker",
                arguments={
                    "intent": "鼓励",
                    "purpose": "explicit_request",
                },
            ),
        )

        self.assertEqual(failed_send.error_code, "sticker_unavailable")
        self.assertEqual(retried_send.status, AgentToolStatus.COMPLETED)
        self.assertEqual(sent, [sticker.sticker_id, sticker.sticker_id])

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
        first_send = await executor.execute(
            ToolExecutionContext(user_id="user_a"),
            AgentToolCall(
                call_id="send_first",
                tool_name="send_sticker",
                arguments={
                    "intent": "开心",
                    "purpose": "explicit_request",
                },
            ),
        )
        second_send = await executor.execute(
            ToolExecutionContext(
                user_id="user_a",
                prior_results=(first_send,),
            ),
            AgentToolCall(
                call_id="send_second",
                tool_name="send_sticker",
                arguments={
                    "intent": "庆祝",
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
            tool_name="send_sticker",
            arguments={
                "intent": "开心",
                "purpose": "explicit_request",
            },
        )
        first = await executor.execute(ToolExecutionContext(user_id="user_a"), call)
        duplicate = await executor.execute(
            ToolExecutionContext(user_id="user_a", prior_results=(first,)),
            AgentToolCall(
                call_id="tool_second",
                tool_name="send_sticker",
                arguments=call.arguments,
            ),
        )

        self.assertEqual(first.status, AgentToolStatus.COMPLETED)
        self.assertEqual(duplicate.error_code, "duplicate_tool_call")
        self.assertEqual(searches, [("user_a", "开心", 3)])

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

    async def test_call_search_reports_progress_once_then_streams_without_tools(self):
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
                            arguments={"query": "今天的新闻", "limit": 1},
                        ),
                    )
                ),
                AgentModelResponse(text="今天比较受关注的是这件事。"),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(model, web_search=web)
        progress = []

        async def record_progress(text):
            progress.append(text)

        result = await orchestrator.execute(
            user_id="user_a",
            message="帮我查一下今天的新闻",
            messages=[{"role": "user", "content": "帮我查一下今天的新闻"}],
            conversation_mode="call",
            allowed_tool_names=("search_web",),
            tool_call_limit=1,
            on_progress_text=record_progress,
        )

        self.assertEqual(progress, ["好，我查一下。"])
        self.assertEqual(_tool_names(model.calls[0]["tools"]), ["search_web"])
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertEqual(result.reply_text, "今天比较受关注的是这件事。")

    async def test_call_search_no_result_cannot_claim_that_results_were_found(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_web_empty",
                            tool_name="search_web",
                            arguments={"query": "不存在的消息", "limit": 1},
                        ),
                    )
                ),
                AgentModelResponse(text="我查到了，确实有这条消息。"),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(model, web_search=FakeWebSearch())

        result = await orchestrator.execute(
            user_id="user_a",
            message="帮我查一下这条消息",
            messages=[{"role": "user", "content": "帮我查一下这条消息"}],
            conversation_mode="call",
            allowed_tool_names=("search_web",),
            tool_call_limit=1,
        )

        self.assertEqual(
            result.reply_text,
            "这次没有查到可靠的结果，我们可以换个说法再试试。",
        )

    async def test_call_search_failure_cannot_claim_that_search_succeeded(self):
        class FailingWebSearch:
            async def search(self, request):
                del request
                raise RuntimeError("provider unavailable")

        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_web_failed",
                            tool_name="search_web",
                            arguments={"query": "今天的新闻", "limit": 1},
                        ),
                    )
                ),
                AgentModelResponse(text="搜索成功，今天有很多新闻。"),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(
            model,
            web_search=FailingWebSearch(),
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="帮我查一下今天的新闻",
            messages=[{"role": "user", "content": "帮我查一下今天的新闻"}],
            conversation_mode="call",
            allowed_tool_names=("search_web",),
            tool_call_limit=1,
        )

        self.assertEqual(result.reply_text, "这次联网查询没有完成，稍后再试试吧。")

    async def test_call_cancel_is_only_exposed_after_listing_owned_schedules(self):
        class ScheduleRepository:
            def __init__(self):
                self.deleted = []

            def list_schedules(self, user_id):
                self.listed_user_id = user_id
                return (
                    SimpleNamespace(
                        schedule_id="schedule_owned",
                        user_visible_label="明天的提醒",
                        intent="提醒我带伞",
                        status="active",
                        next_run_at=datetime(2026, 8, 17, 0, 0, tzinfo=UTC),
                        timezone="Asia/Shanghai",
                    ),
                )

            def delete_schedule(self, user_id, schedule_id):
                self.deleted.append((user_id, schedule_id))
                return user_id == "user_a" and schedule_id == "schedule_owned"

        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_list",
                            tool_name="list_chat_schedules",
                            arguments={"include_inactive": False},
                        ),
                    )
                ),
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="call_cancel",
                            tool_name="cancel_chat_schedule",
                            arguments={"schedule_id": "schedule_owned"},
                        ),
                    )
                ),
                AgentModelResponse(text="好，这个提醒已经取消了。"),
            ]
        )
        schedule_repository = ScheduleRepository()
        registry = ToolRegistry()
        register_schedule_tools(registry, schedule_repository)
        orchestrator = OrchestrateChatWithAgent(
            repository=FakeAgentRunRepository(),
            model=model,
            registry=registry,
            executor=ToolExecutor(registry),
            max_steps=4,
            max_tool_calls=2,
            run_timeout_seconds=45,
        )

        result = await orchestrator.execute(
            user_id="user_a",
            message="取消我明天的提醒",
            messages=[{"role": "user", "content": "取消我明天的提醒"}],
            conversation_mode="call",
            allowed_tool_names=("list_chat_schedules",),
            tool_call_limit=2,
            conversation_id="conv_a",
        )

        self.assertEqual(_tool_names(model.calls[0]["tools"]), ["list_chat_schedules"])
        self.assertEqual(_tool_names(model.calls[1]["tools"]), ["cancel_chat_schedule"])
        self.assertEqual(model.calls[2]["tools"], ())
        self.assertEqual(schedule_repository.listed_user_id, "user_a")
        self.assertEqual(schedule_repository.deleted, [("user_a", "schedule_owned")])
        self.assertEqual(result.reply_text, "好，这个提醒已经取消了。")

    async def test_call_route_rejects_registered_but_unadvertised_tool(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    tool_calls=(
                        AgentToolCall(
                            call_id="unexpected_time",
                            tool_name="get_current_time",
                            arguments={"timezone": "Asia/Shanghai"},
                        ),
                    )
                ),
                AgentModelResponse(text="这次没有执行额外操作。"),
            ]
        )
        orchestrator, _, _ = _build_orchestrator(model)
        progress = []

        async def record_progress(text):
            progress.append(text)

        result = await orchestrator.execute(
            user_id="user_a",
            message="查一下今天的新闻",
            messages=[{"role": "user", "content": "查一下今天的新闻"}],
            conversation_mode="call",
            allowed_tool_names=("search_web",),
            tool_call_limit=1,
            on_progress_text=record_progress,
        )

        self.assertEqual(progress, [])
        self.assertEqual(result.tool_results[0].error_code, "tool_not_allowed_for_route")
        self.assertEqual(result.reply_text, "这次没有执行额外操作。")

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

    async def test_proactive_empty_natural_output_completes_as_a_silent_skip(self):
        model = SequenceAgentModel([AgentModelResponse(text="", finish_reason="stop")])
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="A proactive message is due.",
            messages=[{"role": "system", "content": "internal proactive trigger"}],
            conversation_mode="proactive",
        )

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "")
        self.assertEqual(result.reply_segments, ())
        self.assertEqual(result.content_parts, ())
        self.assertIsNone(result.error_code)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0][2], None)

    async def test_proactive_truncated_empty_output_stays_silent_without_retry(self):
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
        self.assertEqual(len(model.calls), 1)
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

    async def test_protocol_output_is_failed_without_leaking_protocol_fragment(self):
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

    async def test_exact_legacy_json_is_rejected_and_repaired_as_natural_text(self):
        model = SequenceAgentModel(
            [
                AgentModelResponse(
                    text='{"text_segments":["hello"],"sticker_placement":"after_text"}'
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
        self.assertFalse(model.calls[0]["structured_output"])
        self.assertFalse(model.calls[1]["structured_output"])
        self.assertEqual(model.calls[1]["tools"], ())
        self.assertIn("只输出用户可见的自然文字", model.calls[0]["messages"][0]["content"])
        self.assertEqual(repository.finishes[0][2], None)

    async def test_metadata_prefixed_reply_is_recovered_without_another_model_call(self):
        leaked_output = "[消息时间 2026-08-13T09:12:35+08:00 周四 上午]\n我也想再睡会儿。"
        model = SequenceAgentModel(
            [
                AgentModelResponse(text=leaked_output),
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

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, "我也想再睡会儿。")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0][2], None)

    async def test_proactive_metadata_prefixed_control_text_is_never_recovered(self):
        leaked_output = (
            "[消息时间 2026-08-13T09:12:35+08:00 周四 上午]\n"
            "（本条消息为系统生成，无实际文本内容）"
        )
        model = SequenceAgentModel(
            [
                AgentModelResponse(text=leaked_output),
                AgentModelResponse(text=leaked_output),
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
        self.assertEqual(result.error_code, "llm_output_malformed")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0][2], "llm_output_malformed")

    async def test_proactive_initial_context_strips_history_time_metadata(self):
        model = SequenceAgentModel([AgentModelResponse(text=_delivery("有空的时候来聊聊。"))])
        orchestrator, _, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a",
            message="A proactive message is due.",
            messages=[
                {
                    "role": "system",
                    "content": "[会话时间边界] 上一段对话已经结束。",
                },
                {
                    "role": "assistant",
                    "content": "[消息时间 2026-08-13T09:00:00+08:00 周四 上午]\n早上好。",
                },
                {"role": "system", "content": "internal proactive trigger"},
            ],
            conversation_mode="proactive",
        )

        contents = [str(message.get("content") or "") for message in model.calls[0]["messages"]]
        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertFalse(any("[消息时间" in content for content in contents))
        self.assertFalse(any("[会话时间边界" in content for content in contents))
        self.assertIn("早上好。", contents)

    async def test_kaomoji_and_emotional_beats_survive_agent_delivery(self):
        first = "这句夸得我有点得意了 (￣▽￣)"
        second = "你眼光还挺好。"
        model = SequenceAgentModel([AgentModelResponse(text=first + "\n\n" + second)])
        orchestrator, repository, _ = _build_orchestrator(model)

        result = await orchestrator.execute(
            user_id="user_a", message="你刚刚那句好可爱。",
            messages=[{"role": "user", "content": "你刚刚那句好可爱。"}],
        )

        self.assertEqual(result.reply_segments, (first, second))
        self.assertIn("(￣▽￣)", result.reply_text)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(repository.finishes[0][2], None)

    async def test_natural_reply_does_not_require_json_or_retry(self):
        natural_output = "那就再眯一会儿。"
        model = SequenceAgentModel([AgentModelResponse(text=natural_output)])
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

        self.assertEqual(result.status, AgentRunStatus.COMPLETED)
        self.assertEqual(result.reply_text, natural_output)
        self.assertEqual(len(model.calls), 1)
        self.assertFalse(model.calls[0]["structured_output"])
        self.assertEqual(repository.finishes[0][2], None)

    async def test_proactive_protocol_output_failure_is_silent(self):
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
