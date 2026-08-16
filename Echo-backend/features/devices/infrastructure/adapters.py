from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from shared.config import settings

from features.chat.infrastructure.events import ChatEvent, get_chat_event_broker
from features.chat.public import list_chat_messages, send_chat_message
from features.devices.domain.entities import DeviceTurnResult
from features.voice.public import recognize_voice


class EchoVoiceRecognizer:
    async def recognize_pcm16(self, audio_bytes: bytes) -> str:
        result = await recognize_voice(audio_bytes, "audio/L16")
        return result.user_text


class EchoConversationService:
    async def reply(
        self,
        *,
        user_id: str,
        user_text: str,
        request_id: str,
        on_reply_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
        synthesize_voice: bool = True,
    ) -> DeviceTurnResult:
        result = await send_chat_message(
            user_id=user_id,
            message=user_text,
            conversation_mode="call",
            request_id=request_id,
            on_text_delta=on_reply_delta,
            on_progress_text=on_progress_text,
            synthesize_voice=synthesize_voice,
        )
        return DeviceTurnResult(
            user_text=user_text,
            reply=result.reply,
            audio_urls=result.audio_urls,
        )


class EchoSpeechSynthesizer:
    def stream_pcm16(self, text: str) -> AsyncIterator[bytes]:
        from providers.tts_provider import get_tts_provider

        return get_tts_provider().stream_pcm16(
            text,
            settings.tts_voice_id,
            instruction=settings.cosyvoice_instruction,
        )


class EchoAudioSource:
    async def read(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Device TTS URL must use HTTP or HTTPS")
        static_base = urlparse(settings.static_url_prefix)
        if (
            parsed.path.startswith("/static/voices/generated/")
            and parsed.netloc == static_base.netloc
        ):
            filename = Path(unquote(parsed.path)).name
            candidate = (
                Path(__file__).resolve().parents[3]
                / "static"
                / "voices"
                / "generated"
                / filename
            )
            if candidate.is_file():
                return candidate.read_bytes()

        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            if len(response.content) > settings.tts_audio_max_bytes:
                raise ValueError("Device TTS audio exceeds configured size limit")
            return response.content


class EchoChatNotifier:
    async def notify_latest_turn(self, user_id: str) -> None:
        page = list_chat_messages(user_id, limit=2)
        messages = [
            {
                "message_id": item.message_id,
                "stable_message_id": item.stable_message_id,
                "client_message_id": item.client_message_id,
                "role": item.role,
                "message_type": item.message_type,
                "content": item.content,
                "content_parts": [vars(part) for part in item.content_parts],
                "sources": [vars(source) for source in item.sources],
                "agent_turn_id": item.agent_turn_id,
                "reply_group_id": item.reply_group_id,
                "sequence_in_group": item.sequence_in_group,
                "in_reply_to_message_id": item.in_reply_to_message_id,
                "created_at": item.created_at.isoformat(),
            }
            for item in page.items
        ]
        await get_chat_event_broker().publish(
            user_id,
            ChatEvent(
                event="chat.sync",
                data={
                    "conversation_id": page.conversation_id,
                    "messages": messages,
                    "origin": "echo_device",
                },
            ),
        )


def parse_personal_device_map(raw_value: str) -> dict[str, str]:
    if not raw_value.strip():
        return {}
    parsed = json.loads(raw_value)
    if not isinstance(parsed, dict):
        raise ValueError("ECHO_DEVICE_USER_MAP_JSON must be a JSON object")
    mapping = {str(key).strip().lower(): str(value).strip() for key, value in parsed.items()}
    if any(not device_id or not user_id for device_id, user_id in mapping.items()):
        raise ValueError("ECHO_DEVICE_USER_MAP_JSON contains an empty device or user id")
    return mapping
