from typing import Literal

from pydantic import BaseModel, Field


class DeviceFirmwareResponse(BaseModel):
    version: str = ""
    url: str = ""
    sha256: str = ""
    size_bytes: int = 0
    board_type: str = ""
    board_variant: str = ""


class DeviceWebSocketConfig(BaseModel):
    url: str
    token: str
    version: int = Field(default=1, ge=1, le=1)


class DeviceActivationResponse(BaseModel):
    pairing_id: str
    code: str
    message: str = ""
    pairing_only: bool = True


class DeviceBootstrapResponse(BaseModel):
    firmware: DeviceFirmwareResponse
    websocket: DeviceWebSocketConfig
    activation: DeviceActivationResponse | None = None


class DevicePairingResponse(BaseModel):
    pairing_id: str
    code: str
    expires_in: int


class DeviceProvisioningSessionResponse(BaseModel):
    claim_token: str
    expires_in: int


class DevicePairingClaimRequest(BaseModel):
    pairing_id: str = Field(default="", max_length=100)
    code: str = Field(pattern=r"^\d{6}$")


class DeviceCredentialResponse(BaseModel):
    device_id: str
    client_id: str
    credential: str


class DeviceSummary(BaseModel):
    device_id: str
    client_id: str = ""
    display_name: str
    firmware_version: str = ""
    status: Literal["unclaimed", "online", "offline", "revoked"]
    last_seen_at: str | None = None
    wifi_ssid: str = ""
    bound_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DeviceListResponse(BaseModel):
    items: list[DeviceSummary]


class DeviceUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class DeviceHeartbeatRequest(BaseModel):
    firmware_version: str = Field(default="", max_length=80)
    wifi_ssid: str = Field(default="", max_length=128)


class SpeakerProfileResponse(BaseModel):
    speaker_profile_id: str
    display_name: str
    role: str
    status: str
    model_name: str
    model_version: str
    created_at: str | None = None
    updated_at: str | None = None


class SpeakerEnrollmentResponse(BaseModel):
    speaker_profile_id: str
    samples_added: int
    samples_total: int
    quality_score: float
    duration_ms: int
