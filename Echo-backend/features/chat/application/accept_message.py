from __future__ import annotations

import uuid

from shared.config import settings

from features.agent.domain.entities import ContentPart
from features.chat.domain.entities import ChatMessageAcceptance, ChatValidationError
from features.chat.domain.repositories import ChatIntakeRepository


class AcceptChatMessage:
    def __init__(self, repository: ChatIntakeRepository):
        self.repository = repository

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
            if len(clean_text) > settings.chat_message_max_chars:
                raise ChatValidationError(
                    f"Message exceeds {settings.chat_message_max_chars} characters"
                )
            if content_parts:
                raise ChatValidationError("text message cannot include content_parts")
        else:
            stickers = tuple(
                part
                for part in content_parts
                if part.type == "sticker" and part.sticker_id.strip()
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
            quiet_window_ms=settings.chat_batch_quiet_window_ms,
            maximum_window_ms=settings.chat_batch_max_window_ms,
            maximum_batch_messages=settings.chat_batch_max_messages,
            maximum_batch_characters=settings.chat_batch_max_chars,
            maximum_queued_messages=settings.chat_queue_max_messages,
        )
