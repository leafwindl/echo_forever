from __future__ import annotations

import json
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
        return AgentDeliveryPlan((clean_text,))
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
