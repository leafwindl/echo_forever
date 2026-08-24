from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from shared.config import settings

from features.chat.domain.entities import (
    CHAT_CHANNEL_DEVICE,
    CHAT_VISIBILITY_DEVICE_HISTORY,
)
from features.chat.public import send_chat_message
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
        speaker_role: str | None = None,
        speaker_confidence: float = 0.0,
    ) -> DeviceTurnResult:
        send_kwargs = {
            "user_id": user_id,
            "message": user_text,
            "conversation_mode": "call",
            "request_id": request_id,
            "on_text_delta": on_reply_delta,
            "on_progress_text": on_progress_text,
            "synthesize_voice": synthesize_voice,
            "message_channel": CHAT_CHANNEL_DEVICE,
            "message_visibility": CHAT_VISIBILITY_DEVICE_HISTORY,
        }
        if speaker_role is not None:
            send_kwargs.update(
                speaker_role=speaker_role,
                speaker_confidence=speaker_confidence,
                memory_enabled=speaker_role == "owner",
            )
        result = await send_chat_message(
            **send_kwargs,
        )
        return DeviceTurnResult(
            user_text=user_text,
            reply=result.reply,
            audio_urls=result.audio_urls,
            user_message_id=result.user_message_id,
            assistant_message_id=result.assistant_message_id,
            conversation_id=result.conversation_id,
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
        # Device turns remain available to Echo's shared context and memory,
        # but are intentionally absent from the APP's main chat event stream.
        del user_id


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
