from __future__ import annotations

from dataclasses import dataclass

from features.chat.domain.entities import ChatDeliveryPresentation


@dataclass(frozen=True)
class DeliveryTimingPolicy:
    followup_text_delay_ms: int
    final_text_delay_ms: int
    sticker_delay_ms: int

    def build(
        self,
        *,
        delivery_types: tuple[str, ...],
        agent_elapsed_ms: int,
    ) -> ChatDeliveryPresentation:
        delays: list[int] = []
        for delivery_index, delivery_type in enumerate(delivery_types):
            if delivery_type == "sticker":
                delays.append(self.sticker_delay_ms)
                continue

            if delivery_index == 0:
                delays.append(0)
                continue

            delay = self.final_text_delay_ms if delivery_index >= 2 else self.followup_text_delay_ms
            delays.append(delay)

        return ChatDeliveryPresentation(
            agent_elapsed_ms=max(agent_elapsed_ms, 0),
            initial_delay_ms=delays[0] if delays else 0,
            message_delays_ms=tuple(delays),
        )
