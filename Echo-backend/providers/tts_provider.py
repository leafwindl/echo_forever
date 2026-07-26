from dataclasses import dataclass
from typing import Protocol, cast

import edge_tts
import httpx
from shared.config import settings

from providers.registry import get_provider


@dataclass(frozen=True)
class TTSOutput:
    audio_bytes: bytes
    file_suffix: str
    content_type: str


class TTSProvider(Protocol):
    async def text_to_speech(self, text: str, voice_id: str) -> TTSOutput: ...


class EdgeTTSProvider:
    async def text_to_speech(self, text: str, voice_id: str) -> TTSOutput:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("TTS text cannot be empty")

        try:
            communicate = edge_tts.Communicate(clean_text, voice_id)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if not audio_data:
                raise ValueError("Edge TTS returned empty audio")
            return TTSOutput(
                audio_bytes=audio_data,
                file_suffix=".mp3",
                content_type="audio/mpeg",
            )
        except Exception as exc:
            raise ValueError(f"Edge TTS error: {exc}") from exc


class MeloTTSProvider:
    async def text_to_speech(self, text: str, voice_id: str) -> TTSOutput:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("TTS text cannot be empty")

        endpoint = f"{settings.melotts_base_url.rstrip('/')}/synthesize"
        try:
            async with (
                httpx.AsyncClient(timeout=settings.melotts_timeout_seconds) as client,
                client.stream(
                    "POST",
                    endpoint,
                    json={
                        "text": clean_text,
                        "speaker": voice_id,
                        "speed": settings.tts_speed,
                    },
                ) as response,
            ):
                response.raise_for_status()
                audio_buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(audio_buffer) + len(chunk) > settings.tts_audio_max_bytes:
                        raise ValueError("MeloTTS response exceeds configured audio size limit")
                    audio_buffer.extend(chunk)
        except httpx.HTTPError as exc:
            raise ValueError(f"MeloTTS request failed: {exc}") from exc

        audio_bytes = bytes(audio_buffer)
        if not audio_bytes:
            raise ValueError("MeloTTS returned empty audio")
        return TTSOutput(
            audio_bytes=audio_bytes,
            file_suffix=".wav",
            content_type="audio/wav",
        )


def get_tts_provider() -> TTSProvider:
    provider_name = settings.tts_provider.strip().lower()
    if provider_name == "edge":
        return cast(TTSProvider, get_provider("tts", EdgeTTSProvider))
    if provider_name in {"melo", "melotts"}:
        return cast(TTSProvider, get_provider("tts", MeloTTSProvider))
    raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")
