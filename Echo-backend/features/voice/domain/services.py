from typing import Protocol


class VoiceAudioStorage(Protocol):
    def save_upload(self, audio_bytes: bytes, suffix: str = ".mp3") -> str:
        ...

    async def save_generated_audio(self, audio_bytes: bytes) -> str:
        ...


class VoiceRecognizer(Protocol):
    async def recognize(self, audio_path: str) -> str:
        ...


class VoiceSynthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes:
        ...


class VoiceChatResponder(Protocol):
    async def reply(self, user_id: str, message: str) -> str:
        ...
