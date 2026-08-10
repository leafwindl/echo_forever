from __future__ import annotations

import json
import re
from typing import Any

from features.letters.domain.entities import LetterAgentOutput


class LetterOutputValidationError(ValueError):
    """Raised when the Agent did not produce a safe, structured letter."""


def parse_letter_agent_output(
    raw: str,
    *,
    minimum_chars: int,
    maximum_chars: int,
) -> LetterAgentOutput:
    candidate = raw.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LetterOutputValidationError("daily letter output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LetterOutputValidationError("daily letter output must be an object")

    subject = _text(payload.get("subject"), "subject", 120)
    content = _text(payload.get("content"), "content", 4000)
    if len(content) < minimum_chars:
        raise LetterOutputValidationError("daily letter content is shorter than the minimum")
    if len(content) > maximum_chars:
        raise LetterOutputValidationError("daily letter content is longer than the maximum")
    reflection = _text(payload.get("reflection"), "reflection", 1200)
    mood = _text(payload.get("mood"), "mood", 80)
    closing_style = _text(payload.get("closing_style"), "closing_style", 40)
    topics = _texts(payload.get("core_topics"), "core_topics", 8, 80)
    source_message_ids = _positive_ints(payload.get("source_message_ids"), "source_message_ids")
    source_memory_ids = _texts(payload.get("source_memory_ids"), "source_memory_ids", 20, 160)
    image_brief = _image_brief(payload.get("image_brief"))

    return LetterAgentOutput(
        subject=subject,
        content=content,
        mood=mood,
        core_topics=topics,
        reflection=reflection,
        closing_style=closing_style,
        image_brief=image_brief,
        source_message_ids=source_message_ids,
        source_memory_ids=source_memory_ids,
    )


def _text(value: Any, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LetterOutputValidationError(f"{field_name} is required")
    return value.strip()[:maximum]


def _texts(value: Any, field_name: str, maximum_items: int, item_maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LetterOutputValidationError(f"{field_name} must be a list")
    result = tuple(
        item.strip()[:item_maximum]
        for item in value
        if isinstance(item, str) and item.strip()
    )
    if len(result) > maximum_items:
        return result[:maximum_items]
    return result


def _positive_ints(value: Any, field_name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise LetterOutputValidationError(f"{field_name} must be a list")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            continue
        result.append(item)
    if not result:
        raise LetterOutputValidationError(f"{field_name} must contain an id")
    return tuple(dict.fromkeys(result))


def _image_brief(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LetterOutputValidationError("image_brief must be an object")
    emotion = _clean_image_text(value.get("emotion"), "image_brief.emotion", 300)
    scene = _clean_image_text(value.get("scene"), "image_brief.scene", 800)
    symbols = _clean_image_items(value.get("visual_symbols"), "image_brief.visual_symbols")
    avoid = _clean_image_items(value.get("avoid"), "image_brief.avoid")
    return {
        "emotion": emotion,
        "scene": scene,
        "visual_symbols": list(symbols),
        "avoid": list(avoid),
    }


def _clean_image_text(value: Any, field_name: str, maximum: int) -> str:
    text = _text(value, field_name, maximum)
    text = re.sub(r"https?://\S+", "[隐去链接]", text, flags=re.IGNORECASE)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[隐去邮箱]", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[隐去号码]", text)
    return text


def _clean_image_items(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [
            item.strip()
            for item in re.split(r"[\n,，、;；|]+", value)
            if item.strip()
        ]
    if not isinstance(value, list):
        raise LetterOutputValidationError(f"{field_name} must be a list")
    return tuple(
        _clean_image_text(item, field_name, 100)
        for item in value[:12]
        if isinstance(item, str) and item.strip()
    )
