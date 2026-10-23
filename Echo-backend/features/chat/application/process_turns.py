from __future__ import annotations

import logging
import time

from features.chat.application.generate_reply import GenerateChatReply
from features.chat.domain.delivery_timing import DeliveryTimingPolicy
from features.chat.domain.repositories import ChatTurnRepository
from features.chat.domain.services import ChatRequestGuard
from features.chat.infrastructure.events import ChatEvent, ChatEventBroker

logger = logging.getLogger(__name__)


class ProcessPendingChatTurns:
    def __init__(
        self,
        *,
        repository: ChatTurnRepository,
        reply_generator: GenerateChatReply,
        request_guard: ChatRequestGuard,
        event_broker: ChatEventBroker,
        timing_policy: DeliveryTimingPolicy,
        lease_seconds: int,
    ):
        self.repository = repository
        self.reply_generator = reply_generator
        self.request_guard = request_guard
        self.event_broker = event_broker
        self.timing_policy = timing_policy
        self.lease_seconds = lease_seconds

    async def run_once(self) -> bool:
        turn = self.repository.claim_due_turn(self.lease_seconds)
        if turn is None:
            return False
        if not self.request_guard.try_acquire(turn.user_id):
            self.repository.reschedule_turn(turn.turn_id, 250)
            return True

        await self.event_broker.publish(
            turn.user_id,
            ChatEvent(
                event="chat.typing.started",
                data={
                    "turn_id": turn.turn_id,
                    "conversation_id": turn.conversation_id,
                },
            ),
        )
        started_at = time.perf_counter()
        try:
            batch = self.repository.load_batch(turn)
            prepared = await self.reply_generator.prepare(
                user_id=turn.user_id,
                message=batch.combined_content,
                conversation_id=turn.conversation_id,
                conversation_mode="chat",
                sticker_intent=batch.sticker_intent,
                history_before_message_id=turn.input_first_message_id,
            )
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            sticker_count = sum(
                part.type == "sticker" and bool(part.sticker_id) for part in prepared.content_parts
            )
            delivery_types: list[str] = []
            if sticker_count and prepared.sticker_placement == "before_text":
                delivery_types.extend("sticker" for _ in range(sticker_count))
            delivery_types.extend("text" for _ in prepared.reply_segments)
            if sticker_count and prepared.sticker_placement != "before_text":
                delivery_types.extend("sticker" for _ in range(sticker_count))
            if not delivery_types:
                delivery_types.append("text")
            presentation = self.timing_policy.build(
                delivery_types=tuple(delivery_types),
                agent_elapsed_ms=elapsed_ms,
                text_segments=prepared.reply_segments,
            )
            group = self.repository.complete_turn(turn, prepared, presentation)
            if group is None:
                return True
            try:
                await self.reply_generator.finalize_persisted_turn(
                    user_id=turn.user_id,
                    conversation_id=turn.conversation_id,
                    user_message=batch.combined_content,
                    assistant_reply=prepared.reply,
                    source_message_id=turn.input_last_message_id,
                )
            except Exception:
                logger.warning(
                    "Queued chat post-processing failed turn_id=%s",
                    turn.turn_id,
                    exc_info=True,
                )
            await self.event_broker.publish(
                turn.user_id,
                ChatEvent(
                    event="chat.delivery.created",
                    data=self._reply_group_payload(group),
                ),
            )
            logger.info(
                "Queued chat turn completed turn_id=%s message_count=%s deliveries=%s "
                "duration_ms=%s",
                turn.turn_id,
                turn.message_count,
                len(group.messages),
                elapsed_ms,
            )
            return True
        except Exception as exc:
            error_code = type(exc).__name__[:120]
            self.repository.fail_turn(turn.turn_id, error_code)
            logger.exception("Queued chat turn failed turn_id=%s", turn.turn_id)
            await self.event_broker.publish(
                turn.user_id,
                ChatEvent(
                    event="chat.turn.failed",
                    data={
                        "turn_id": turn.turn_id,
                        "conversation_id": turn.conversation_id,
                        "error_code": error_code,
                    },
                ),
            )
            return True
        finally:
            self.request_guard.release(turn.user_id)
            await self.event_broker.publish(
                turn.user_id,
                ChatEvent(
                    event="chat.typing.stopped",
                    data={
                        "turn_id": turn.turn_id,
                        "conversation_id": turn.conversation_id,
                    },
                ),
            )

    @staticmethod
    def _reply_group_payload(group) -> dict[str, object]:
        return {
            "turn_id": group.turn_id,
            "reply_group_id": group.reply_group_id,
            "conversation_id": group.conversation_id,
            "presentation": {
                "agent_elapsed_ms": group.presentation.agent_elapsed_ms,
                "initial_delay_ms": group.presentation.initial_delay_ms,
                "message_delays_ms": list(group.presentation.message_delays_ms),
            },
            "messages": [
                {
                    "message_id": message.message_id,
                    "stable_message_id": message.stable_message_id,
                    "client_message_id": message.client_message_id,
                    "role": message.role,
                    "message_type": message.message_type,
                    "content": message.content,
                    "content_parts": [
                        {
                            "type": part.type,
                            "text": part.text,
                            "sticker_id": part.sticker_id,
                            "url": part.url,
                        }
                        for part in message.content_parts
                    ],
                    "sources": [
                        {
                            "title": source.title,
                            "url": source.url,
                            "snippet": source.snippet,
                            "published_at": source.published_at,
                        }
                        for source in message.sources
                    ],
                    "agent_turn_id": message.agent_turn_id,
                    "reply_group_id": message.reply_group_id,
                    "sequence_in_group": message.sequence_in_group,
                    "in_reply_to_message_id": message.in_reply_to_message_id,
                    "created_at": message.created_at.isoformat(),
                }
                for message in group.messages
            ],
        }
