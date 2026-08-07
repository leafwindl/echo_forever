from __future__ import annotations

from shared.config import settings

from features.chat.domain.entities import ChatDeliveryPresentation


class DeliveryTimingPolicy:
    def build(
        self,
        *,
        text_segments: tuple[str, ...],
        delivery_types: tuple[str, ...],
        agent_elapsed_ms: int,
    ) -> ChatDeliveryPresentation:
        delays: list[int] = []
        for delivery_index, delivery_type in enumerate(delivery_types):
            if delivery_type == "sticker":
                delays.append(settings.chat_sticker_delay_ms)
                continue

            if delivery_index == 0:
                delays.append(0)
                continue

            delay = (
                settings.chat_final_text_delay_ms
                if delivery_index >= 2
                else settings.chat_followup_text_delay_ms
            )
            delays.append(delay)

        return ChatDeliveryPresentation(
            agent_elapsed_ms=max(agent_elapsed_ms, 0),
            initial_delay_ms=delays[0] if delays else 0,
            message_delays_ms=tuple(delays),
        )
