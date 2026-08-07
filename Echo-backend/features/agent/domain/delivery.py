from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDeliveryPlan:
    text_segments: tuple[str, ...]
    sticker_placement: str = "after_text"

    @property
    def reply_text(self) -> str:
        return "\n".join(self.text_segments)


def parse_agent_delivery_plan(raw_text: str, conversation_mode: str) -> AgentDeliveryPlan:
    clean_text = raw_text.strip()
    if not clean_text:
        return AgentDeliveryPlan(())
    if conversation_mode == "call":
        return AgentDeliveryPlan((clean_text,))

    candidate = clean_text
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return AgentDeliveryPlan(_fallback_segments(clean_text))
    if not isinstance(payload, dict):
        return AgentDeliveryPlan((clean_text,))
    raw_segments = payload.get("text_segments")
    if not isinstance(raw_segments, list):
        return AgentDeliveryPlan((clean_text,))

    segments: list[str] = []
    for value in raw_segments:
        if not isinstance(value, str):
            continue
        segment = value.strip()
        if not segment or (segments and segments[-1] == segment):
            continue
        segments.append(segment)
        if len(segments) == 3:
            break
    placement = str(payload.get("sticker_placement") or "after_text").strip().lower()
    if placement not in {"before_text", "after_text"}:
        placement = "after_text"
    return AgentDeliveryPlan(tuple(segments), placement)


def _fallback_segments(text: str) -> tuple[str, ...]:
    if len(text) < 24 or _should_keep_single_segment(text):
        return (text,)
    sentences = [
        value.strip()
        for value in re.findall(r".*?(?:[。！？!?；;]+|$)", text, flags=re.S)
        if value.strip()
    ]
    if len(sentences) < 2 and len(text) >= 80:
        sentences = [
            value.strip()
            for value in re.findall(r".*?(?:[，,。！？!?；;]+|$)", text, flags=re.S)
            if value.strip()
        ]
    if len(sentences) < 2:
        return (text,)

    target_count = 2 if len(text) < 80 else 3
    segments: list[str] = []
    current = ""
    target_length = max(len(text) // target_count, 12)
    for sentence in sentences:
        current += sentence
        remaining_slots = target_count - len(segments) - 1
        if len(current) >= target_length and remaining_slots > 0:
            segments.append(current.strip())
            current = ""
    if current.strip():
        segments.append(current.strip())
    if len(segments) < 2 or any(len(segment) < 6 for segment in segments):
        return (text,)
    if len(segments) > 3:
        segments = [*segments[:2], "".join(segments[2:])]
    return tuple(segments)


def _should_keep_single_segment(text: str) -> bool:
    return bool(
        "```" in text
        or "http://" in text
        or "https://" in text
        or "|" in text
        or re.search(r"(?m)^\s*(?:[-*]|\d+[.)、])\s+", text)
    )
