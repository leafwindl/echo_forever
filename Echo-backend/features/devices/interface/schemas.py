from pydantic import BaseModel, Field


class DeviceFirmwareResponse(BaseModel):
    version: str = ""
    url: str = ""


class DeviceWebSocketConfig(BaseModel):
    url: str
    token: str
    version: int = Field(default=1, ge=1, le=1)


class DeviceBootstrapResponse(BaseModel):
    firmware: DeviceFirmwareResponse
    websocket: DeviceWebSocketConfig
