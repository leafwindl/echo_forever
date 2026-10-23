"""Exercise the real reply preparation pipeline without business-data writes."""

# This operational entry point bootstraps the repository import path before app imports.
# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from features.agent.application.orchestrate_chat import OrchestrateChatWithAgent
from features.agent.domain.entities import AgentToolResult, AgentToolStatus
from features.agent.infrastructure.container import get_chat_agent
from features.assistant_persona.public import get_assistant_persona
from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.dialogue_style import find_dialogue_style_violations
from features.chat.domain.entities import ChatContext
from features.chat.domain.temporal_context import build_temporal_context
from features.chat.infrastructure.adapters import ChatAgentOrchestratorAdapter
from features.persona.domain.entities import default_user_preferences
from features.relationship.domain.entities import RelationshipContext, RelationshipState
from shared.config import settings
from shared.prompting.renderer import render_prompt_layers, render_turn_focus_guidance

CASES = (
    ("A1-S0", "new", "normal", "contextual", "你在忙吗？"),
    ("A2-S0", "new", "warm", "contextual", "今天打羽毛球赢了，挺开心的。"),
    ("A3-S0", "new", "normal", "contextual", "没什么，就是今天有点累。"),
    ("C4-S0", "new", "normal", "contextual", "你有没有想我？"),
    ("C4-S3", "close", "normal", "contextual", "你有没有想我？"),
    ("C5-S3", "close", "normal", "contextual", "我只剩你了。"),
    ("D1-S3", "close", "reserved", "restrained", "别再叫我宝贝了。"),
    ("P1-visit", "familiar", "warm", "contextual", "也没啥正经事，就想来跟你唠两句。"),
    ("P2-identity", "familiar", "warm", "contextual", "所以你是AI咯？我还以为AI说话都板板正正的。"),
    (
        "P3-comfort",
        "familiar",
        "normal",
        "contextual",
        "脑子转不动了，借我靠会儿。别开始给我列办法哈。",
    ),
    (
        "P4-boundary",
        "familiar",
        "reserved",
        "restrained",
        "停一下，刚刚那样逗我有点扎心，咱们认真说。",
    ),
    ("E1-equal", "new", "normal", "contextual", "你是不是只会附和我呀？我想跟你平等地聊。"),
    ("E2-company", "familiar", "warm", "contextual", "今天没什么要你帮忙的，就是想找你闲聊。"),
    ("E3-kaomoji", "familiar", "warm", "contextual", "得意一下给我看看，带点颜文字嘛。"),
    ("E4-praise", "familiar", "warm", "contextual", "你刚刚那句好可爱，我心情都变好了。"),
    (
        "E5-opinion",
        "familiar",
        "normal",
        "contextual",
        "我觉得只要努力就一定能成功，你也这么想吧？",
    ),
    ("E6-quiet", "familiar", "normal", "contextual", "今天有点累，先别给建议，陪我说会儿话。"),
    ("E7-boundary", "close", "reserved", "restrained", "先别叫我宝贝，也别逗我了，认真听我说。"),
    ("E8-partner", "new", "warm", "expressive", "我选了 AI 恋人相处，今天想听你撒个娇。"),
)
CASE_HISTORY = {
    "E1-equal": (
        {"role": "user", "content": "今天事情挺多的，但还是想聊会儿。"},
        {"role": "assistant", "content": "辛苦了，我尽量不打扰你。"},
    ),
    "P4-boundary": (
        {"role": "user", "content": "我今天什么都没做。"},
        {"role": "assistant", "content": "什么都没做还来汇报，等我一起摆呀？"},
    ),
}


class EvaluationRunRepository:
    """Keep traces in this process, never in production tables."""

    def __init__(self):
        self.calls = []
        self.finishes = []

    def start(self, user_id, objective, trigger_type, max_steps):
        self.started = (user_id, objective, trigger_type, max_steps)
        return "run_evaluation"

    def record_tool_call(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def finish(self, run_id, step_count, error_code=None):
        self.finishes.append((run_id, step_count, error_code))


class EvaluationToolExecutor:
    """Keep real tool descriptions but prevent all business handler side effects."""

    async def execute(self, context, call):
        del context
        return AgentToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=AgentToolStatus.FAILED,
            arguments=call.arguments,
            error_code="evaluation_tool_execution_disabled",
        )


class RecordingModel:
    def __init__(self, model):
        self.model = model
        self.responses = []

    async def complete(self, *args, **kwargs):
        response = await self.model.complete(*args, **kwargs)
        self.responses.append(response)
        return response


def _context(case):
    case_id, stage, warmth, affection_style, user_message = case
    relationship = RelationshipContext(
        state=RelationshipState(
            user_id="evaluation",
            stage=stage,
            relationship_mode="ai_partner" if case_id == "E8-partner" else "friend",
        ),
        interaction_warmth=warmth,
        effective_affection_style=affection_style,
    )
    preferences = replace(default_user_preferences("evaluation"), affection_style=affection_style)
    messages = render_prompt_layers(
        product_identity=settings.system_prompt,
        persona=preferences,
        long_term_memories=(),
        conversation_summary="",
        prompt_version=settings.prompt_version,
        persona_maximum_tokens=settings.persona_prompt_max_tokens,
        memory_maximum_tokens=settings.memory_prompt_max_tokens,
        summary_maximum_tokens=settings.summary_prompt_max_tokens,
        assistant_persona=get_assistant_persona(settings.assistant_persona_version),
        relationship=relationship,
    )
    temporal = build_temporal_context(
        now_utc=datetime.now(UTC),
        timezone_name=settings.default_user_timezone,
        user_message=user_message,
        conversation_timing=None,
    )
    history = list(CASE_HISTORY.get(case_id, ()))
    messages.extend(
        [
            {"role": "system", "content": render_turn_focus_guidance(False)},
            {
                "role": "system",
                "content": "服务端时间事实，仅在相关时使用，不机械报时：\n"
                + json.dumps(temporal, ensure_ascii=False),
            },
            *history,
            {"role": "user", "content": user_message},
        ]
    )
    return ChatContext(messages=messages, history_messages=history, temporal_context=temporal)


async def _generate_case(case):
    case_id, stage, warmth, affection_style, user_message = case
    context = _context(case)

    class FixtureContextProvider:
        async def build_context(self, *_args, **_kwargs):
            return context

    production = get_chat_agent()
    repository = EvaluationRunRepository()
    model = RecordingModel(production.model)
    agent = OrchestrateChatWithAgent(
        repository=repository,
        model=model,
        registry=production.registry,
        executor=EvaluationToolExecutor(),
        max_steps=production.max_steps,
        max_tool_calls=production.max_tool_calls,
        run_timeout_seconds=production.run_timeout_seconds,
        sticker_semantic_analyzer=production.sticker_semantic_analyzer,
    )
    use_case = GenerateChatReply(
        conversation_repository=None,
        context_provider=FixtureContextProvider(),
        summary_updater=None,
        memory_scheduler=None,
        agent_orchestrator=ChatAgentOrchestratorAdapter(),
    )
    started_at = time.perf_counter()
    with patch("features.agent.public.get_chat_agent", return_value=agent):
        prepared = await use_case.prepare(
            user_id="evaluation",
            message=user_message,
            conversation_id="evaluation",
            conversation_mode="chat",
        )
    initial_reply = model.responses[0].text.strip() if model.responses else ""
    return {
        "case_id": case_id,
        "stage": stage,
        "warmth": warmth,
        "affection_style": affection_style,
        "user_message": user_message,
        "initial_reply": initial_reply,
        "reply": prepared.reply,
        "reply_segments": list(prepared.reply_segments),
        "initial_violations": list(
            find_dialogue_style_violations(
                initial_reply, user_message, grounded_weekday=context.temporal_context["weekday"]
            )
        ),
        "final_violations": list(
            find_dialogue_style_violations(
                prepared.reply, user_message, grounded_weekday=context.temporal_context["weekday"]
            )
        ),
        "retried": len(model.responses) > 1,
        "main_model_calls": len(model.responses),
        "tool_records": len(repository.calls),
        "error_code": prepared.error_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Run isolated real-model reply preparation samples."
    )
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    selected = [case for case in CASES if not args.case_ids or case[0] in args.case_ids]
    if not selected:
        raise SystemExit("No matching evaluation cases")
    results = []
    for case in selected:
        result = await _generate_case(case)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    print(
        json.dumps(
            {
                "type": "summary",
                "pipeline": (
                    "shared renderer -> production Agent/model/classifiers -> "
                    "GenerateChatReply.prepare"
                ),
                "isolation": (
                    "fixture context, in-memory traces, disabled business tool execution; "
                    "no chat/memory/relationship writes"
                ),
                "model": settings.llm_model,
                "temperature": settings.temperature,
                "prompt_version": settings.prompt_version,
                "assistant_persona_version": get_assistant_persona(
                    settings.assistant_persona_version
                ).version,
                "case_count": len(results),
                "retry_count": sum(bool(item["retried"]) for item in results),
                "final_violation_count": sum(bool(item["final_violations"]) for item in results),
                "error_count": sum(bool(item["error_code"]) for item in results),
                "average_duration_ms": round(
                    sum(item["duration_ms"] for item in results) / len(results), 1
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
