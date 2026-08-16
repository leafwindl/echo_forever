from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NATURAL_DELIVERY_MODES = frozenset({"chat", "proactive"})
_STICKER_PLACEMENTS = frozenset({"before_text", "after_text"})
_NATURAL_MAX_TEXT_SEGMENTS = 6
_NATURAL_SEGMENT_TARGET_CHARS = 180
_INTERNAL_CONTEXT_MARKER = re.compile(
    r"[\[\uff3b]\s*(?:\u6d88\u606f\u65f6\u95f4|\u4f1a\u8bdd\u65f6\u95f4\u8fb9\u754c)",
    flags=re.IGNORECASE,
)
_DELIVERY_PROTOCOL_FIELD = re.compile(
    r'"(?:text_segments|sticker_placement|tool_name|tool_calls|call_id|safe_for_model|'
    r'agent_turn_id|job_id|error_code|sticker_id|content_parts)"',
    flags=re.IGNORECASE,
)
_INTERNAL_IDENTIFIER = re.compile(
    r"\b(?:run|job|msg|conv|stk|schedule)_[A-Za-z0-9]+\b",
    flags=re.IGNORECASE,
)
_INTERNAL_CONTROL_MARKER = re.compile(
    r"(?:"
    r"\u672c\u6761\u6d88\u606f.{0,12}\u7cfb\u7edf\u751f\u6210|"
    r"\u672c\u6761\u6d88\u606f.{0,12}\u53ef\u4fe1\u7ed3\u6784\u5316\u9644\u4ef6|"
    r"\u65e0\u5b9e\u9645\u6587\u672c\u5185\u5bb9|"
    r"\u540e\u7aef\u6279\u51c6\u7684\u4e3b\u52a8\u804a\u5929\u5199\u4f5c\u7b80\u62a5|"
    r"\u552f\u4e00\u5141\u8bb8\u4f7f\u7528\u7684\u4e8b\u5b9e|"
    r"system[- ]generated\s+proactive\s+trigger|"
    r"not\s+an\s+incoming\s+user\s+message|"
    r"use\s+the\s+following\s+intent\s+as\s+internal\s+context\s+only"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class AgentDeliveryPlan:
    text_segments: tuple[str, ...]
    sticker_placement: str = "after_text"

    @property
    def reply_text(self) -> str:
        return "\n".join(self.text_segments)


class AgentDeliveryPlanError(ValueError):
    """The model did not satisfy the final delivery contract."""

    error_code = "llm_output_malformed"


def validate_agent_delivery_segments(segments: tuple[str, ...]) -> None:
    """Apply the same content gate immediately before chat persistence."""
    if len(segments) > _NATURAL_MAX_TEXT_SEGMENTS:
        raise AgentDeliveryPlanError("Delivery contains too many text segments")
    seen: set[str] = set()
    for value in segments:
        if not isinstance(value, str) or not value.strip():
            raise AgentDeliveryPlanError("Delivery contains an invalid text segment")
        segment = value.strip()
        if segment in seen:
            raise AgentDeliveryPlanError("Delivery contains duplicate text segments")
        _validate_delivery_segment(segment)
        seen.add(segment)


def _validate_delivery_segment(segment: str) -> None:
    normalized = unicodedata.normalize("NFKC", segment)
    if normalized.lstrip().startswith(("{", "[", "```")):
        raise AgentDeliveryPlanError("Delivery contains protocol-like output")
    if _INTERNAL_CONTEXT_MARKER.search(normalized):
        raise AgentDeliveryPlanError("Delivery leaked internal time context")
    if _DELIVERY_PROTOCOL_FIELD.search(normalized):
        raise AgentDeliveryPlanError("Delivery contains a nested protocol fragment")
    if _INTERNAL_IDENTIFIER.search(normalized):
        raise AgentDeliveryPlanError("Delivery contains an internal identifier")
    if _INTERNAL_CONTROL_MARKER.search(normalized):
        raise AgentDeliveryPlanError("Delivery leaked internal control context")


def build_natural_delivery_plan(
    raw_text: str,
    conversation_mode: str,
    *,
    sticker_placement: str = "after_text",
    allow_empty: bool = False,
) -> AgentDeliveryPlan:
    """Build the transport plan from natural model text.

    Chat and proactive replies accept only natural user-visible text. Protocol
    JSON and Markdown fences are rejected instead of being interpreted.
    """
    if conversation_mode == "daily_letter":
        clean = raw_text.strip()
        return AgentDeliveryPlan((clean,)) if clean else AgentDeliveryPlan(())
    if conversation_mode == "call":
        clean = raw_text.strip()
        if not clean and not allow_empty:
            raise AgentDeliveryPlanError("Delivery output is empty")
        segments = (clean,) if clean else ()
        validate_agent_delivery_segments(segments)
        return AgentDeliveryPlan(segments)
    if conversation_mode not in _NATURAL_DELIVERY_MODES:
        raise AgentDeliveryPlanError("Unknown natural delivery mode")
    if sticker_placement not in _STICKER_PLACEMENTS:
        raise AgentDeliveryPlanError("sticker_placement has an invalid value")

    clean = raw_text.strip()
    if not clean:
        if allow_empty:
            return AgentDeliveryPlan((), sticker_placement)
        raise AgentDeliveryPlanError("Natural delivery output is empty")

    normalized_clean = unicodedata.normalize("NFKC", clean)
    if normalized_clean.startswith(("{", "[", "```")) or _DELIVERY_PROTOCOL_FIELD.search(
        normalized_clean
    ):
        raise AgentDeliveryPlanError("Delivery contains protocol or JSON output")
    if _INTERNAL_IDENTIFIER.search(normalized_clean):
        raise AgentDeliveryPlanError("Delivery contains an internal identifier")
    if _INTERNAL_CONTEXT_MARKER.search(normalized_clean) or _INTERNAL_CONTROL_MARKER.search(
        normalized_clean
    ):
        raise AgentDeliveryPlanError("Delivery leaked internal control context")

    paragraphs = [part.strip() for part in re.split(r"\n+", clean) if part.strip()]
    if not paragraphs:
        raise AgentDeliveryPlanError("Natural delivery output is empty")

    segments: list[str] = []
    for paragraph in paragraphs:
        segments.extend(_split_long_paragraph(paragraph))
    segments = _fit_segment_limit(segments)
    normalized = tuple(segment.strip() for segment in segments if segment.strip())
    validate_agent_delivery_segments(normalized)
    return AgentDeliveryPlan(normalized, sticker_placement)


def _split_long_paragraph(paragraph: str) -> list[str]:
    if len(paragraph) <= _NATURAL_SEGMENT_TARGET_CHARS:
        return [paragraph]
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?])\s*", paragraph)
        if part.strip()
    ]
    if len(sentences) <= 1:
        return [paragraph]
    result: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current}{sentence}" if current else sentence
        if current and len(candidate) > _NATURAL_SEGMENT_TARGET_CHARS:
            result.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        result.append(current)
    return result


def _fit_segment_limit(segments: list[str]) -> list[str]:
    if len(segments) <= _NATURAL_MAX_TEXT_SEGMENTS:
        return segments
    head = segments[: _NATURAL_MAX_TEXT_SEGMENTS - 1]
    tail = "\n\n".join(segments[_NATURAL_MAX_TEXT_SEGMENTS - 1 :]).strip()
    return [*head, tail]
