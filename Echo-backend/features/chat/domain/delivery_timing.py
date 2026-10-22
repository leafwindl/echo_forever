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
        text_segments: tuple[str, ...] = (),
    ) -> ChatDeliveryPresentation:
        delays: list[int] = []
        text_index = 0
        for delivery_index, delivery_type in enumerate(delivery_types):
            if delivery_type == "sticker":
                delay = min(max(self.sticker_delay_ms, 0), 400)
            else:
                cap = (
                    self.final_text_delay_ms if text_index >= 2 else self.followup_text_delay_ms
                )
                if text_index < len(text_segments):
                    visible_chars = sum(not char.isspace() for char in text_segments[text_index])
                    delay = min(max(cap, 0), 240 + visible_chars * 24)
                else:
                    delay = max(cap, 0)
                text_index += 1
            # Generation has already taken time. Reveal the first available part now.
            delays.append(0 if delivery_index == 0 else delay)

        # Long helpful answers must not turn into a lengthy simulated typing queue.
        total_delay = sum(delays)
        if total_delay > 3000:
            delays = [delay * 3000 // total_delay for delay in delays]

        return ChatDeliveryPresentation(
            agent_elapsed_ms=max(agent_elapsed_ms, 0),
            initial_delay_ms=delays[0] if delays else 0,
            message_delays_ms=tuple(delays),
        )
