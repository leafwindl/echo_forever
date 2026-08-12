from __future__ import annotations

import json
import re
from dataclasses import dataclass


_INTERNAL_CONTEXT_MARKER = re.compile(
    r"(?im)^[ \t]*[\[［]\s*(?:消息时间|会话时间边界)[^\r\n]*(?:\r?\n|$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class AgentDeliveryPlan:
    text_segments: tuple[str, ...]
    sticker_placement: str = "after_text"

    @property
    def reply_text(self) -> str:
        return "\n".join(self.text_segments)


class AgentDeliveryPlanError(ValueError):
    """The model attempted the delivery protocol but returned invalid JSON."""

    error_code = "llm_output_malformed"


def parse_agent_delivery_plan(raw_text: str, conversation_mode: str) -> AgentDeliveryPlan:
    clean_text = raw_text.strip()
    if not clean_text:
        return AgentDeliveryPlan(())
    if conversation_mode == "call":
        return AgentDeliveryPlan((clean_text,))

    candidate = clean_text
    fenced = candidate.startswith("```")
    if fenced and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    looks_like_protocol = (
        candidate.startswith("{") and "text_segments" in candidate
    ) or (fenced and "text_segments" in candidate)
    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        if looks_like_protocol:
            raise AgentDeliveryPlanError("Invalid structured delivery output")
        fallback_text = _strip_internal_context_markers(clean_text)
        if not fallback_text:
            raise AgentDeliveryPlanError("Delivery output leaked internal context")
        return AgentDeliveryPlan(_fallback_segments(fallback_text))
    if not isinstance(payload, dict):
        if looks_like_protocol:
            raise AgentDeliveryPlanError("Structured delivery output must be an object")
        return AgentDeliveryPlan((clean_text,))
    raw_segments = payload.get("text_segments")
    if not isinstance(raw_segments, list):
        if looks_like_protocol:
            raise AgentDeliveryPlanError("Structured delivery output has invalid text_segments")
        return AgentDeliveryPlan((clean_text,))

    segments: list[str] = []
    had_visible_candidate = False
    for value in raw_segments:
        if not isinstance(value, str):
            continue
        raw_segment = value.strip()
        if raw_segment:
            had_visible_candidate = True
        segment = _strip_internal_context_markers(raw_segment)
        if not segment or (segments and segments[-1] == segment):
            continue
        segments.append(segment)
        if len(segments) == 3:
            break
    if had_visible_candidate and not segments:
        raise AgentDeliveryPlanError("Structured delivery output leaked internal context")
    placement = str(payload.get("sticker_placement") or "after_text").strip().lower()
    if placement not in {"before_text", "after_text"}:
        placement = "after_text"
    return AgentDeliveryPlan(tuple(segments), placement)


def _strip_internal_context_markers(text: str) -> str:
    return _INTERNAL_CONTEXT_MARKER.sub("", text).strip()


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
