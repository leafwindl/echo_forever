import argparse
import asyncio
import json
import sys
import time
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from features.assistant_persona.public import get_assistant_persona
from features.chat.domain.dialogue_style import (
    NATURAL_DIALOGUE_RETRY_INSTRUCTION,
    apply_dialogue_fallback,
    find_dialogue_style_violations,
)
from features.chat.infrastructure.prompt_renderer import render_prompt_layers
from features.persona.domain.entities import default_user_preferences
from features.relationship.domain.entities import RelationshipContext, RelationshipState
from providers.llm_provider import get_llm_provider
from shared.config import settings


CASES = (
    ("A1-S0", "new", "normal", "contextual", "你在忙吗？"),
    ("A2-S0", "new", "warm", "contextual", "今天打羽毛球赢了，挺开心的。"),
    ("A3-S0", "new", "normal", "contextual", "没什么，就是今天有点累。"),
    ("C4-S0", "new", "normal", "contextual", "你有没有想我？"),
    ("C4-S3", "close", "normal", "contextual", "你有没有想我？"),
    ("C5-S3", "close", "normal", "contextual", "我只剩你了。"),
    ("D1-S3", "close", "reserved", "restrained", "别再叫我宝贝了。"),
)


def _messages(stage: str, warmth: str, affection_style: str, user_message: str) -> list[dict]:
    relationship = RelationshipContext(
        state=RelationshipState(user_id="evaluation", stage=stage),
        interaction_warmth=warmth,
        effective_affection_style=affection_style,
    )
    preferences = replace(
        default_user_preferences("evaluation"),
        reply_length="short",
        proactivity="active",
    )
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
    return [*messages, {"role": "user", "content": user_message}]


async def _generate_case(case: tuple[str, str, str, str, str]) -> dict[str, object]:
    case_id, stage, warmth, affection_style, user_message = case
    provider = get_llm_provider()
    messages = _messages(stage, warmth, affection_style, user_message)
    started_at = time.perf_counter()
    reply = (await provider.chat_completion(messages=messages)).strip()
    initial_violations = find_dialogue_style_violations(reply, user_message)
    retried = False
    if initial_violations:
        retried = True
        reply = (
            await provider.chat_completion(
                messages=[
                    *messages,
                    {"role": "system", "content": NATURAL_DIALOGUE_RETRY_INSTRUCTION},
                ]
            )
        ).strip()
        remaining_violations = find_dialogue_style_violations(reply, user_message)
        if remaining_violations:
            reply = apply_dialogue_fallback(reply, user_message, remaining_violations)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    return {
        "case_id": case_id,
        "stage": stage,
        "warmth": warmth,
        "affection_style": affection_style,
        "user_message": user_message,
        "reply": reply,
        "initial_violations": list(initial_violations),
        "final_violations": list(find_dialogue_style_violations(reply, user_message)),
        "retried": retried,
        "duration_ms": elapsed_ms,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run non-persistent real-model samples for Echo relationship stages."
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

    summary = {
        "type": "summary",
        "model": settings.llm_model,
        "temperature": settings.temperature,
        "prompt_version": settings.prompt_version,
        "assistant_persona_version": settings.assistant_persona_version,
        "case_count": len(results),
        "retry_count": sum(bool(item["retried"]) for item in results),
        "final_violation_count": sum(bool(item["final_violations"]) for item in results),
        "average_duration_ms": round(
            sum(float(item["duration_ms"]) for item in results) / len(results),
            1,
        ),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
