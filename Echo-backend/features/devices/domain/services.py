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
    ) -> DeviceTurnResult: ...


class DeviceAudioSource(Protocol):
    async def read(self, url: str) -> bytes: ...


class DeviceChatNotifier(Protocol):
    async def notify_latest_turn(self, user_id: str) -> None: ...
