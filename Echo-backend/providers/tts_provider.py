from typing import Protocol, cast

import edge_tts

from providers.registry import get_provider


class TTSProvider(Protocol):
    async def text_to_speech(self, text: str, voice_id: str) -> bytes:
        ...


class EdgeTTSProvider:
    async def text_to_speech(self, text: str, voice_id: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("TTS text cannot be empty")

        try:
            communicate = edge_tts.Communicate(clean_text, voice_id)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as exc:
            raise ValueError(f"Edge TTS error: {exc}") from exc


def get_tts_provider() -> TTSProvider:
    return cast(TTSProvider, get_provider("tts", EdgeTTSProvider))
