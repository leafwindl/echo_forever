"""P0.0 基线：在改关系阶段之前，记录当前固定层渲染结果。

只读：不连接数据库、不调用模型、不写业务表。
输出一份 Markdown，用于后续 R1-R3 对比层数、字数和文本变化。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Echo-backend"))

from features.assistant_persona.public import get_assistant_persona  # noqa: E402
from features.persona.domain.entities import PersonaUpdate, build_user_preferences  # noqa: E402
from features.relationship.domain.entities import (  # noqa: E402
    RelationshipContext,
    RelationshipState,
)
from shared.prompting.renderer import (  # noqa: E402
    estimate_prompt_tokens,
    render_prompt_layers,
)


def _profile(
    *,
    display_name: str = "",
    basics: dict[str, str] | None = None,
    routine: dict[str, str] | None = None,
    interests: tuple[str, ...] = (),
    boundaries: tuple[str, ...] = (),
) -> SimpleNamespace:
    basics = basics or {}
    routine = routine or {}
    return SimpleNamespace(
        display_name=display_name,
        basics=basics,
        routine=routine,
        personality="",
        communication="",
        interests=interests,
        boundaries=boundaries,
        notes="",
        confidence={},
        is_empty=not any((display_name, basics, routine, interests, boundaries)),
    )


def _persona(
    *,
    preferred_name: str | None = None,
    about_user: str | None = None,
    reply_style: str = "natural",
    reply_length: str = "balanced",
    proactivity: str = "balanced",
    avoid_topics: tuple[str, ...] = (),
):
    return build_user_preferences(
        "eval-user",
        PersonaUpdate(
            preferred_name=preferred_name,
            about_user=about_user,
            reply_style=reply_style,
            reply_length=reply_length,
            proactivity=proactivity,
            avoid_topics=avoid_topics,
        ),
        is_customized=bool(preferred_name or about_user or avoid_topics),
        onboarding_completed=True,
    )


def _relationship(stage: str, relationship_type: str = "acquaintance") -> RelationshipContext:
    return RelationshipContext(
        state=RelationshipState(
            user_id="eval-user",
            stage=stage,
            relationship_type=relationship_type,
        ),
        interaction_warmth="normal",
        effective_affection_style="contextual",
    )


CASES = [
    ("初识｜空画像", "chat", "new", "acquaintance", _profile(), _persona(), "", []),
    (
        "初识｜有称呼",
        "chat",
        "new",
        "acquaintance",
        _profile(display_name="叶子"),
        _persona(preferred_name="叶子"),
        "",
        [],
    ),
    (
        "熟悉｜基本画像",
        "chat",
        "familiar",
        "friend",
        _profile(
            display_name="叶子",
            basics={"职业": "研究生", "城市": "武汉"},
            routine={"睡觉": "一两点"},
            interests=("AI", "散步"),
        ),
        _persona(preferred_name="叶子", reply_style="concise"),
        "用户最近在准备考试。",
        [
            {"memory_type": "preference", "content": "用户不喜欢模板化安慰"},
            {"memory_type": "event", "content": "用户上周说想学吉他"},
        ],
    ),
    (
        "信任｜有边界",
        "chat",
        "trusted",
        "friend",
        _profile(
            display_name="叶子",
            basics={"职业": "研究生"},
            interests=("AI",),
            boundaries=("家庭",),
        ),
        _persona(preferred_name="叶子", avoid_topics=("家庭",)),
        "用户和 Echo 聊过学习计划。",
        [{"memory_type": "goal", "content": "用户想完成毕业论文"}],
    ),
    (
        "亲近｜完整偏好",
        "chat",
        "close",
        "partner",
        _profile(
            display_name="叶子",
            basics={"职业": "研究生", "城市": "武汉"},
            routine={"睡觉": "一两点", "上课": "上午"},
            interests=("AI", "散步", "音乐"),
        ),
        _persona(
            preferred_name="叶子",
            about_user="在开发 Echo",
            reply_style="lively",
            reply_length="short",
            proactivity="active",
        ),
        "用户在开发 Echo，最近在调整人设。",
        [{"memory_type": "preference", "content": "用户喜欢直接给结论"}],
    ),
    (
        "通话｜初识",
        "call",
        "new",
        "acquaintance",
        _profile(),
        _persona(),
        "",
        [],
    ),
    (
        "通话｜熟悉",
        "call",
        "familiar",
        "friend",
        _profile(display_name="叶子", basics={"职业": "研究生"}),
        _persona(preferred_name="叶子"),
        "用户刚下班。",
        [{"memory_type": "event", "content": "用户今天面试"}],
    ),
    (
        "主动 writer｜熟悉",
        "proactive",
        "familiar",
        "friend",
        _profile(display_name="叶子", interests=("AI",)),
        _persona(preferred_name="叶子"),
        "用户最近在准备考试。",
        [],
    ),
    (
        "主动 writer｜亲近",
        "proactive",
        "close",
        "partner",
        _profile(display_name="叶子", basics={"职业": "研究生"}),
        _persona(preferred_name="叶子"),
        "用户和 Echo 刚聊完一天的事。",
        [],
    ),
    (
        "每日来信｜熟悉",
        "daily_letter",
        "familiar",
        "friend",
        _profile(display_name="叶子", interests=("AI",)),
        _persona(preferred_name="叶子"),
        "",
        [{"memory_type": "event", "content": "用户昨天完成了面试"}],
    ),
    ("长偏好｜简短", "chat", "familiar", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子", reply_length="short"), "", []),
    ("长偏好｜详细", "chat", "familiar", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子", reply_length="detailed"), "", []),
    ("支持方式｜安慰", "chat", "familiar", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子", reply_style="concise"), "", []),
    ("主动程度｜安静", "chat", "new", "acquaintance", _profile(), _persona(proactivity="quiet"), "", []),
    ("主动程度｜活跃", "chat", "familiar", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子", proactivity="active"), "", []),
    ("避免话题｜家庭", "chat", "familiar", "friend", _profile(display_name="叶子", boundaries=("家庭",)), _persona(preferred_name="叶子", avoid_topics=("家庭",)), "", []),
    ("空画像｜自定义偏好", "chat", "new", "acquaintance", _profile(), _persona(preferred_name="叶子", about_user="不喜欢模板化安慰"), "", []),
    ("熟悉｜高优先级记忆", "chat", "familiar", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子"), "用户最近在准备考试。", [
        {"memory_type": "preference", "content": "用户喜欢安静", "similarity_score": 0.9},
        {"memory_type": "event", "content": "用户上周说想学吉他", "similarity_score": 0.8},
        {"memory_type": "goal", "content": "用户想完成毕业论文", "similarity_score": 0.7},
    ]),
    ("信任｜长摘要", "chat", "trusted", "friend", _profile(display_name="叶子"), _persona(preferred_name="叶子"), "用户最近在准备考试，晚上常熬夜，白天上课。", []),
    ("亲近｜完整上下文", "chat", "close", "partner", _profile(display_name="叶子", basics={"职业": "研究生"}, routine={"睡觉": "一两点"}, interests=("AI", "音乐")), _persona(preferred_name="叶子", about_user="在开发 Echo"), "用户在开发 Echo。", [
        {"memory_type": "preference", "content": "用户喜欢直接给结论"},
        {"memory_type": "event", "content": "用户昨天完成了面试"},
    ]),
]


def _render_case(case):
    label, mode, stage, relationship_type, profile, persona, summary, memories = case
    assistant_persona = get_assistant_persona("echo-persona-v5")
    messages = render_prompt_layers(
        persona=persona,
        long_term_memories=memories,
        conversation_summary=summary,
        persona_maximum_tokens=400,
        memory_maximum_tokens=800,
        summary_maximum_tokens=800,
        assistant_persona=assistant_persona,
        relationship=_relationship(stage, relationship_type),
        user_profile=profile,
        conversation_mode=mode,
    )
    total_chars = sum(len(str(message.get("content") or "")) for message in messages)
    total_tokens = sum(
        estimate_prompt_tokens(str(message.get("content") or "")) for message in messages
    )
    return {
        "label": label,
        "mode": mode,
        "stage": stage,
        "relationship_type": relationship_type,
        "messages": messages,
        "chars": total_chars,
        "tokens": total_tokens,
    }


def _markdown(results, out_path: Path) -> None:
    lines = [
        "# 人设提示词基线（P0.0）",
        "",
        "日期：2026-11-27。状态：**改关系阶段之前的只读快照**。",
        "",
        "用途：R1-R3 改完后对比层数、字数、文本变化；不调用模型、不写业务表。",
        "",
        "| 场景 | 模式 | 阶段 | 类型 | 层数 | 字数 | 估算 token |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r['label']} | {r['mode']} | {r['stage']} | {r['relationship_type']} | "
            f"{len(r['messages'])} | {r['chars']} | {r['tokens']} |"
        )
    lines.append("")
    for r in results:
        lines.extend([f"## {r['label']}", ""])
        for index, message in enumerate(r["messages"], start=1):
            content = str(message.get("content") or "")
            lines.extend(
                [
                    f"### 第 {index} 层 · {message.get('role')} · {len(content)} 字",
                    "",
                    "```text",
                    content,
                    "```",
                    "",
                ]
            )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(ROOT / "doc" / "persona-baseline-2026-11-27.md"),
    )
    args = parser.parse_args()
    results = [_render_case(case) for case in CASES]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _markdown(results, out_path)
    print(f"wrote {out_path} ({len(results)} cases)")


if __name__ == "__main__":
    main()
