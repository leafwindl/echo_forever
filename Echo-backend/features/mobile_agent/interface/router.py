from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from shared.interface.dependencies import CurrentUser, get_current_user
from shared.security import RateLimitExceeded, RateLimitRule, request_limiter

from features.mobile_agent.application.skills import (
    AppSkillError,
    run_app_skill,
)
from features.mobile_agent.domain.entities import (
    MobileAgentActionError,
    MobileAgentError,
    MobileAgentOfflineError,
    MobileAgentPairingError,
    MobileAgentTimeoutError,
)
from features.mobile_agent.infrastructure.container import (
    get_mobile_agent_hub,
    get_mobile_agent_service,
)
from features.mobile_agent.interface.schemas import (
    AppSkillRequest,
    AppSkillResponse,
    MobileAgentAuditItem,
    MobileAgentAuditResponse,
    MobileAgentCommandRequest,
    MobileAgentCommandResponse,
    MobileAgentDeviceListResponse,
    MobileAgentDeviceResponse,
    PairingCodeResponse,
    PairMobileAgentRequest,
    PairMobileAgentResponse,
)

router = APIRouter(prefix="/mobile-agent", tags=["mobile-agent"])


def _client_fingerprint(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    return hashlib.sha256(host.encode("utf-8")).hexdigest()[:24]


def _consume_pair_limit(request: Request) -> None:
    try:
        request_limiter.consume(
            [
                RateLimitRule(
                    key=f"mobile-agent-pair:{_client_fingerprint(request)}",
                    requests=8,
                    window_seconds=60,
                )
            ]
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many mobile agent pairing attempts",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def _device_response(device, online: bool) -> MobileAgentDeviceResponse:
    return MobileAgentDeviceResponse(
        device_id=device.device_id,
        name=device.name,
        status=device.status,
        online=online,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
    )


def _validate_command(action: str, arguments: dict[str, Any]) -> dict[str, Any]:
    action = action.strip()
    if action in {"observe", "screenshot", "notifications", "stop"}:
        return {}
    if action == "launch_app":
        package = str(arguments.get("package") or "").strip()
        if not package or len(package) > 200:
            raise ValueError("package is required")
        return {"package": package}
    if action == "open_uri":
        uri = str(arguments.get("uri") or "").strip()
        if not (
            uri.startswith("http://")
            or uri.startswith("https://")
            or uri.startswith("orpheus://")
            or uri.startswith("bilibili://")
            or uri.startswith("snssdk1128://")
        ):
            raise ValueError("unsupported uri scheme")
        if len(uri) > 2000:
            raise ValueError("uri is too long")
        return {"uri": uri}
    if action == "action":
        kind = str(arguments.get("kind") or "").strip()
        if kind == "tap":
            x = int(arguments.get("x") or 0)
            y = int(arguments.get("y") or 0)
            return {"kind": "tap", "x": x, "y": y}
        if kind == "tap_text":
            text = str(arguments.get("text") or "").strip()
            if not text:
                raise ValueError("text is required")
            return {"kind": "tap_text", "text": text[:200]}
        if kind in {"back", "home", "recents"}:
            return {"kind": kind}
        if kind == "input_text":
            text = str(arguments.get("text") or "")
            if not text or len(text) > 2000:
                raise ValueError("text is required")
            return {"kind": "input_text", "text": text}
        if kind == "swipe":
            return {
                "kind": "swipe",
                "x1": int(arguments.get("x1") or 0),
                "y1": int(arguments.get("y1") or 0),
                "x2": int(arguments.get("x2") or 0),
                "y2": int(arguments.get("y2") or 0),
                "duration_ms": int(arguments.get("duration_ms") or 300),
            }
        if kind == "key":
            keycode = int(arguments.get("keycode") or 0)
            if keycode <= 0 or keycode > 300:
                raise ValueError("valid keycode is required")
            return {"kind": "key", "keycode": keycode}
        if kind == "text":
            text = str(arguments.get("text") or "")
            if not text or len(text) > 2000:
                raise ValueError("text is required")
            return {"kind": "text", "text": text}
        raise ValueError("unsupported action kind")
    raise ValueError("unsupported action")


@router.post("/pairing-codes", response_model=PairingCodeResponse)
def create_pairing_code(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    result = get_mobile_agent_service().create_pairing_code(current_user.user_id)
    return PairingCodeResponse(code=result.code, expires_at=result.expires_at)


@router.post("/pair", response_model=PairMobileAgentResponse)
def pair_device(payload: PairMobileAgentRequest, request: Request):
    _consume_pair_limit(request)
    try:
        paired = get_mobile_agent_service().pair_device(
            code=payload.code,
            device_name=payload.name,
        )
    except MobileAgentPairingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc
    return PairMobileAgentResponse(
        device=_device_response(paired.device, False),
        token=paired.token,
    )


@router.post("/unpair", status_code=status.HTTP_204_NO_CONTENT)
def unpair_device(request: Request):
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    service = get_mobile_agent_service()
    device = service.authenticate(token)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid mobile agent token",
        )
    service.revoke(device.user_id, device.device_id)
    return None


@router.get("/devices", response_model=MobileAgentDeviceListResponse)
def list_devices(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    service = get_mobile_agent_service()
    hub = get_mobile_agent_hub()
    return MobileAgentDeviceListResponse(
        items=[
            _device_response(device, hub.is_online(device.device_id))
            for device in service.list_devices(current_user.user_id)
        ]
    )


@router.post(
    "/skills/{skill}/{action}",
    response_model=AppSkillResponse,
)
async def run_skill(
    skill: str,
    action: str,
    payload: AppSkillRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    try:
        result = await run_app_skill(
            user_id=current_user.user_id,
            skill=skill,
            action=action,
            parameters={
                "query": payload.query,
                "text": payload.text,
                "count": payload.count,
            },
            device_id=payload.device_id,
        )
    except AppSkillError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except MobileAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return AppSkillResponse(
        skill=result.skill,
        device_id=result.device_id,
        action=result.action,
        data=result.data,
    )


@router.get("/audit", response_model=MobileAgentAuditResponse)
def get_audit(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = 50,
):
    rows = get_mobile_agent_service().list_actions(current_user.user_id, limit)
    return MobileAgentAuditResponse(
        items=[MobileAgentAuditItem(**row) for row in rows]
    )


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    service = get_mobile_agent_service()
    if not service.revoke(current_user.user_id, device_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="设备不存在",
        )
    await get_mobile_agent_hub().disconnect(device_id)


@router.post(
    "/devices/{device_id}/command",
    response_model=MobileAgentCommandResponse,
)
async def execute_command(
    device_id: str,
    payload: MobileAgentCommandRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    try:
        arguments = _validate_command(payload.action, payload.arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    try:
        result = await get_mobile_agent_service().execute(
            user_id=current_user.user_id,
            device_id=device_id,
            action=payload.action,
            arguments=arguments,
            timeout_seconds=payload.timeout_seconds,
        )
    except MobileAgentOfflineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    except MobileAgentTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except MobileAgentActionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        ) from exc
    except MobileAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc
    return MobileAgentCommandResponse(
        command_id=result.command_id,
        device_id=result.device_id,
        data=result.data,
    )


class _WebSocketChannel:
    def __init__(self, websocket: WebSocket, device):
        self.websocket = websocket
        self.device = device
        self.device_id = device.device_id
        self.user_id = device.user_id

    async def send(self, payload: dict) -> None:
        await self.websocket.send_json(payload)

    async def close(self) -> None:
        await self.websocket.close(code=4403, reason="mobile agent revoked")


@router.websocket("/ws")
async def mobile_agent_ws(websocket: WebSocket):
    authorization = websocket.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    service = get_mobile_agent_service()
    device = service.authenticate(token)
    if device is None:
        await websocket.close(code=4401, reason="invalid mobile agent token")
        return

    channel = _WebSocketChannel(websocket, device)
    hub = get_mobile_agent_hub()
    await websocket.accept()
    hub.register(device, channel)
    service.mark_online(device.device_id)
    try:
        await websocket.send_json(
            {
                "type": "hello_ack",
                "device_id": device.device_id,
                "server_time": datetime.now(UTC).isoformat(),
            }
        )
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                continue
            hub.handle_message(device, payload)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(device)
        service.mark_offline(device.device_id)
