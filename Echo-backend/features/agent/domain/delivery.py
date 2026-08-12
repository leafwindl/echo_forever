from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_STRUCTURED_DELIVERY_MODES = frozenset({"chat", "proactive"})
_DELIVERY_FIELDS = frozenset({"text_segments", "sticker_placement"})
_STICKER_PLACEMENTS = frozenset({"before_text", "after_text"})
_INTERNAL_CONTEXT_MARKER = re.compile(
    r"[\[\uff3b]\s*(?:\u6d88\u606f\u65f6\u95f4|\u4f1a\u8bdd\u65f6\u95f4\u8fb9\u754c)",
    flags=re.IGNORECASE,
)
_DELIVERY_PROTOCOL_FIELD = re.compile(
    r'"(?:text_segments|sticker_placement)"',
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
    """The model did not satisfy the final delivery contract."""

    error_code = "llm_output_malformed"


def parse_agent_delivery_plan(raw_text: str, conversation_mode: str) -> AgentDeliveryPlan:
    if not isinstance(raw_text, str):
        raise AgentDeliveryPlanError("Delivery output must be text")
    clean_text = raw_text.strip()

    if conversation_mode in {"call", "daily_letter"}:
        return AgentDeliveryPlan((clean_text,)) if clean_text else AgentDeliveryPlan(())
    if conversation_mode not in _STRUCTURED_DELIVERY_MODES:
        raise AgentDeliveryPlanError("Unknown structured delivery mode")
    if not clean_text:
        raise AgentDeliveryPlanError("Structured delivery output is empty")

    payload = _load_delivery_payload(clean_text)
    if not isinstance(payload, dict):
        raise AgentDeliveryPlanError("Structured delivery output must be an object")
    if frozenset(payload) != _DELIVERY_FIELDS:
        raise AgentDeliveryPlanError("Structured delivery output has invalid fields")

    raw_segments = payload["text_segments"]
    if not isinstance(raw_segments, list):
        raise AgentDeliveryPlanError("text_segments must be an array")
    if len(raw_segments) > 3:
        raise AgentDeliveryPlanError("text_segments exceeds the maximum item count")

    segments: list[str] = []
    for value in raw_segments:
        if not isinstance(value, str):
            raise AgentDeliveryPlanError("Every text segment must be a string")
        segment = value.strip()
        if not segment:
            raise AgentDeliveryPlanError("Text segments must not be blank")
        if segment in segments:
            raise AgentDeliveryPlanError("Text segments must not be duplicated")
        _validate_delivery_segment(segment)
        segments.append(segment)

    placement = payload["sticker_placement"]
    if not isinstance(placement, str) or placement not in _STICKER_PLACEMENTS:
        raise AgentDeliveryPlanError("sticker_placement has an invalid value")
    return AgentDeliveryPlan(tuple(segments), placement)


def validate_agent_delivery_segments(segments: tuple[str, ...]) -> None:
    """Apply the same content gate immediately before chat persistence."""
    if len(segments) > 3:
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


def _load_delivery_payload(candidate: str) -> Any:
    try:
        return json.loads(
            candidate,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except AgentDeliveryPlanError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AgentDeliveryPlanError("Structured delivery output is not valid JSON") from exc


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AgentDeliveryPlanError("Structured delivery output has duplicate fields")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AgentDeliveryPlanError(f"Structured delivery output contains {value}")


def _validate_delivery_segment(segment: str) -> None:
    if _INTERNAL_CONTEXT_MARKER.search(segment):
        raise AgentDeliveryPlanError("Delivery leaked internal time context")
    if _DELIVERY_PROTOCOL_FIELD.search(segment):
        raise AgentDeliveryPlanError("Delivery contains a nested protocol fragment")
