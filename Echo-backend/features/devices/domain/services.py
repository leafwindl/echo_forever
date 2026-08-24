from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from features.devices.domain.entities import DeviceTurnResult


class DeviceVoiceRecognizer(Protocol):
    async def recognize_pcm16(self, audio_bytes: bytes) -> str: ...


class DeviceConversationService(Protocol):
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
    ) -> DeviceTurnResult: ...


class DeviceSpeechSynthesizer(Protocol):
    def stream_pcm16(
        self,
        text: str,
    ) -> AsyncIterator[bytes]: ...


class DeviceAudioSource(Protocol):
    async def read(self, url: str) -> bytes: ...


class DeviceChatNotifier(Protocol):
    async def notify_latest_turn(self, user_id: str) -> None: ...
