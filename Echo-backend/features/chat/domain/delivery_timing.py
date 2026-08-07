from __future__ import annotations

import unicodedata

from shared.config import settings

from features.chat.domain.entities import ChatDeliveryPresentation

ZERO_WIDTH_JOINER = "\u200d"
VARIATION_SELECTORS = range(0xFE00, 0xFE10)


def count_effective_graphemes(value: str) -> int:
    count = 0
    joined = False
    for character in value:
        codepoint = ord(character)
        if character == ZERO_WIDTH_JOINER:
            joined = True
            continue
        if unicodedata.combining(character) or codepoint in VARIATION_SELECTORS:
            continue
        if joined:
            joined = False
            continue
        count += 1
    return count


class DeliveryTimingPolicy:
    def build(
        self,
        *,
        text_segments: tuple[str, ...],
        delivery_types: tuple[str, ...],
        agent_elapsed_ms: int,
    ) -> ChatDeliveryPresentation:
        segment_lengths = [max(count_effective_graphemes(segment), 1) for segment in text_segments]
        total_characters = sum(segment_lengths)
        target = settings.chat_typing_base_ms + (
            total_characters * settings.chat_typing_per_grapheme_ms
        )
        target = min(max(target, settings.chat_typing_min_ms), settings.chat_typing_max_ms)
        extra_budget = min(
            max(target - max(agent_elapsed_ms, 0), 0),
            settings.chat_typing_extra_max_ms,
        )

        delays: list[int] = []
        text_index = 0
        remaining_budget = extra_budget
        remaining_characters = total_characters
        for delivery_type in delivery_types:
            if delivery_type == "sticker":
                sticker_delay = min(300, remaining_budget)
                delays.append(sticker_delay)
                remaining_budget -= sticker_delay
                continue
            length = segment_lengths[text_index] if text_index < len(segment_lengths) else 1
            text_index += 1
            if remaining_budget <= 0 or remaining_characters <= 0:
                delays.append(0)
                remaining_characters -= length
                continue
            proportional = round(remaining_budget * length / remaining_characters)
            delay = min(
                max(proportional, settings.chat_typing_segment_min_ms),
                settings.chat_typing_segment_max_ms,
                remaining_budget,
            )
            delays.append(delay)
            remaining_budget -= delay
            remaining_characters -= length

        return ChatDeliveryPresentation(
            agent_elapsed_ms=max(agent_elapsed_ms, 0),
            initial_delay_ms=delays[0] if delays else 0,
            message_delays_ms=tuple(delays),
        )
