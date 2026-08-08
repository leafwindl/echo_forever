from __future__ import annotations

import uuid
from dataclasses import dataclass

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import ChatMessageAcceptance, ChatValidationError
from features.chat.domain.repositories import ChatIntakeRepository


@dataclass(frozen=True)
class ChatIntakePolicy:
    message_max_chars: int
    quiet_window_ms: int
    maximum_window_ms: int
    maximum_batch_messages: int
    maximum_batch_characters: int
    maximum_queued_messages: int


class AcceptChatMessage:
    def __init__(self, repository: ChatIntakeRepository, policy: ChatIntakePolicy):
        self.repository = repository
        self.policy = policy

    def execute(
        self,
        *,
        user_id: str,
        client_message_id: str,
        message_type: str,
        text: str = "",
        content_parts: tuple[ContentPart, ...] = (),
    ) -> ChatMessageAcceptance:
        clean_user_id = user_id.strip()
        clean_client_message_id = client_message_id.strip()
        clean_type = message_type.strip().lower()
        clean_text = text.strip()
        if not clean_user_id:
            raise ChatValidationError("user_id is required")
        try:
            uuid.UUID(clean_client_message_id)
        except (ValueError, AttributeError) as exc:
            raise ChatValidationError("client_message_id must be a UUID") from exc
        if clean_type not in {"text", "sticker"}:
            raise ChatValidationError("message_type must be text or sticker")
        if clean_type == "text":
            if not clean_text:
                raise ChatValidationError("text message must not be empty")
            if len(clean_text) > self.policy.message_max_chars:
                raise ChatValidationError(
                    f"Message exceeds {self.policy.message_max_chars} characters"
                )
            if content_parts:
                raise ChatValidationError("text message cannot include content_parts")
        else:
            stickers = tuple(
                part for part in content_parts if part.type == "sticker" and part.sticker_id.strip()
            )
            if len(stickers) != 1 or len(content_parts) != 1:
                raise ChatValidationError("sticker message requires one sticker content part")
            content_parts = stickers

        return self.repository.accept_message(
            user_id=clean_user_id,
            client_message_id=clean_client_message_id,
            message_type=clean_type,
            content=clean_text,
            content_parts=content_parts,
            quiet_window_ms=self.policy.quiet_window_ms,
            maximum_window_ms=self.policy.maximum_window_ms,
            maximum_batch_messages=self.policy.maximum_batch_messages,
            maximum_batch_characters=self.policy.maximum_batch_characters,
            maximum_queued_messages=self.policy.maximum_queued_messages,
        )
