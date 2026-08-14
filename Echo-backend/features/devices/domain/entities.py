from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceAudioFormat:
    sample_rate: int
    channels: int
    frame_duration_ms: int
    format: str = "opus"


@dataclass(frozen=True)
class DeviceConfiguration:
    websocket_url: str
    token: str
    protocol_version: int = 1


@dataclass(frozen=True)
class DeviceTurnResult:
    user_text: str
    reply: str
    audio_urls: tuple[str, ...]
