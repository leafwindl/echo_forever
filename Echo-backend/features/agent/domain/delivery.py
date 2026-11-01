from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass

from features.agent.domain.entities import ContentPart

_NATURAL_DELIVERY_MODES = frozenset({"chat", "proactive"})
_STICKER_PLACEMENTS = frozenset({"before_text", "after_text"})
_NATURAL_MAX_TEXT_SEGMENTS = 10
_NATURAL_SEGMENT_TARGET_CHARS = 180
_NATURAL_SHORT_SPLIT_MIN_CHARS = 45
_NATURAL_SHORT_SPLIT_PERCENT = 55
_CONNECTIVE_PREFIXES = (
    "不过",
    "但是",
    "可是",
    "所以",
    "因为",
    "然后",
    "而且",
    "只是",
    "就是",
    "再说",
    "其实",
)
_STRUCTURED_BLOCK = re.compile(r"```|~~~|(?m:^\s*(?:[-*+]\s|\d+[.)、]\s|\||>\s))")
_URL_OR_INLINE_CODE = re.compile(r"https?://\S+|`[^`]+`")
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


@dataclass(frozen=True)
class DeliveryItem:
    message_type: str
    content: str
    parts: tuple[ContentPart, ...] = ()


def build_delivery_items(
    text_segments: tuple[str, ...],
    content_parts: tuple[ContentPart, ...] = (),
    sticker_placement: str = "after_text",
) -> tuple[DeliveryItem, ...]:
    """Interleave text and stickers while preserving a requested beat index."""
    texts = tuple(segment.strip() for segment in text_segments if segment.strip())
    indexed: dict[int, list[ContentPart]] = {}
    global_parts: list[ContentPart] = []
    for part in content_parts:
        if part.type != "sticker":
            global_parts.append(part)
            continue
        if part.after_text_index >= 0:
            indexed.setdefault(part.after_text_index, []).append(part)
        else:
            global_parts.append(part)

    items: list[DeliveryItem] = []
    if global_parts and sticker_placement == "before_text":
        items.extend(
            DeliveryItem("sticker", "", (part,)) for part in global_parts
        )
    for index, text in enumerate(texts):
        items.append(DeliveryItem("text", text))
        items.extend(
            DeliveryItem("sticker", "", (part,))
            for part in indexed.get(index, ())
        )
    for index in sorted(indexed):
        if index < len(texts):
            continue
        items.extend(
            DeliveryItem("sticker", "", (part,)) for part in indexed[index]
        )
    if global_parts and sticker_placement != "before_text":
        items.extend(
            DeliveryItem("sticker", "", (part,)) for part in global_parts
        )
    return tuple(items)


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

    # Lists/code/table line breaks are formatting, not separate chat messages.
    # Protect multiline quotations as well as the short symbolic kaomoji below.
    preserve_layout = _STRUCTURED_BLOCK.search(clean) or re.search(
        r'[“「『"][^”」』"]*\n', clean
    )
    paragraphs = (
        [clean]
        if preserve_layout
        else [part.strip() for part in re.split(r"\n+", clean) if part.strip()]
    )
    if not paragraphs:
        raise AgentDeliveryPlanError("Natural delivery output is empty")

    segments: list[str] = []
    for paragraph in paragraphs:
        segments.extend(
            [paragraph] if preserve_layout else _split_natural_paragraph(paragraph)
        )
    segments = _fit_segment_limit(segments)
    normalized = tuple(segment.strip() for segment in segments if segment.strip())
    validate_agent_delivery_segments(normalized)
    return AgentDeliveryPlan(normalized, sticker_placement)


def _split_natural_paragraph(paragraph: str) -> list[str]:
    if _URL_OR_INLINE_CODE.search(paragraph):
        return [paragraph]
    sentences = _complete_sentences(paragraph)
    if len(sentences) <= 1:
        return [paragraph]
    if len(paragraph) > _NATURAL_SEGMENT_TARGET_CHARS:
        return _group_sentences(
            sentences,
            maximum_chars=_NATURAL_SEGMENT_TARGET_CHARS,
            maximum_groups=_NATURAL_MAX_TEXT_SEGMENTS,
        )
    if sum(len(sentence.strip()) for sentence in sentences) < _NATURAL_SHORT_SPLIT_MIN_CHARS:
        return [paragraph]
    # Keep the same reply stable across retries while allowing some short
    # multi-sentence replies to form two or three natural bubbles.
    if zlib.crc32(paragraph.encode("utf-8")) % 100 >= _NATURAL_SHORT_SPLIT_PERCENT:
        return [paragraph]
    return _group_sentences(sentences)


def _group_sentences(
    sentences: list[str],
    maximum_chars: int = 120,
    maximum_groups: int = _NATURAL_MAX_TEXT_SEGMENTS,
) -> list[str]:
    groups: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        starts_with_connector = sentence.lstrip().startswith(_CONNECTIVE_PREFIXES)
        too_short_to_stand = len(sentence.strip()) < 8
        would_overflow = len(current) + len(sentence) > maximum_chars
        if starts_with_connector or too_short_to_stand or would_overflow:
            current = f"{current}{sentence}"
        else:
            groups.append(current)
            current = sentence
    if current:
        groups.append(current)
    if len(groups) > maximum_groups:
        groups = [*groups[: maximum_groups - 1], "".join(groups[maximum_groups - 1 :])]
    return groups


def _complete_sentences(text: str) -> list[str]:
    """Only use punctuation outside quotations/brackets as a fallback boundary."""
    pairs = {"(": ")", "（": "）", "[": "]", "【": "】", "“": "”", "「": "」", "『": "』"}
    closing: list[str] = []
    result: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if closing and char == closing[-1]:
            closing.pop()
        elif char == '"':
            if closing and closing[-1] == '"':
                closing.pop()
            else:
                closing.append('"')
        elif char in pairs:
            closing.append(pairs[char])
        elif char in "。！？!?；;" and not closing:
            result.append(text[start : index + 1])
            start = index + 1
    if start < len(text):
        result.append(text[start:])
    return result


def _fit_segment_limit(segments: list[str]) -> list[str]:
    if len(segments) <= _NATURAL_MAX_TEXT_SEGMENTS:
        return segments
    head = segments[: _NATURAL_MAX_TEXT_SEGMENTS - 1]
    tail = "\n\n".join(segments[_NATURAL_MAX_TEXT_SEGMENTS - 1 :]).strip()
    return [*head, tail]
