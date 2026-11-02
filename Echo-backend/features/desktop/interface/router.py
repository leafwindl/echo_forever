from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Annotated

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

from features.desktop.domain.entities import DesktopNode, DesktopPairingError
from features.desktop.infrastructure.container import get_desktop_node_hub, get_desktop_service
from features.desktop.interface.schemas import (
    DesktopNodeListResponse,
    DesktopNodeResponse,
    PairDesktopNodeRequest,
    PairDesktopNodeResponse,
)
from features.desktop.public import (
    authenticate_desktop_node,
    list_desktop_nodes,
    pair_desktop_node,
    revoke_desktop_node,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/desktop", tags=["desktop"])


def _client_fingerprint(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    return hashlib.sha256(host.encode("utf-8")).hexdigest()[:24]


def _consume_pairing_limit(request: Request) -> None:
    try:
        request_limiter.consume(
            [
                RateLimitRule(
                    key=f"desktop-pair:{_client_fingerprint(request)}",
                    requests=8,
                    window_seconds=60,
                )
            ]
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many desktop pairing attempts",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def _node_response(node, online: bool) -> DesktopNodeResponse:
    return DesktopNodeResponse(
        node_id=node.node_id,
        name=node.name,
        capabilities=list(node.capabilities),
        online=online,
        last_seen_at=node.last_seen_at,
        created_at=node.created_at,
    )


@router.post("/nodes/pair", response_model=PairDesktopNodeResponse)
def pair_node(payload: PairDesktopNodeRequest, request: Request):
    _consume_pairing_limit(request)
    try:
        paired = pair_desktop_node(
            code=payload.code,
            node_name=payload.name,
            fingerprint=payload.fingerprint,
            capabilities=tuple(payload.capabilities),
        )
    except DesktopPairingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    return PairDesktopNodeResponse(
        node_id=paired.node.node_id,
        user_id=paired.node.user_id,
        name=paired.node.name,
        token=paired.token,
        capabilities=list(paired.node.capabilities),
    )


@router.get("/nodes", response_model=DesktopNodeListResponse)
def get_nodes(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    nodes = list_desktop_nodes(current_user.user_id)
    return DesktopNodeListResponse(
        items=[_node_response(item.node, item.online) for item in nodes]
    )


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    if not revoke_desktop_node(current_user.user_id, node_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")
    await get_desktop_node_hub().disconnect_node(node_id)


class _WebSocketChannel:
    def __init__(self, websocket: WebSocket, node: DesktopNode):
        self.websocket = websocket
        self.node = node
        self.node_id = node.node_id
        self.user_id = node.user_id
        self.capabilities = node.capabilities

    async def send(self, payload: dict) -> None:
        await self.websocket.send_json(payload)

    async def close(self) -> None:
        await self.websocket.close(code=4403, reason="desktop node revoked")


@router.websocket("/nodes/ws")
async def desktop_node_ws(websocket: WebSocket):
    authorization = websocket.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    node = authenticate_desktop_node(token)
    if node is None:
        await websocket.close(code=4401, reason="invalid desktop node token")
        return

    channel = _WebSocketChannel(websocket, node)
    hub = get_desktop_node_hub()
    service = get_desktop_service()
    await websocket.accept()
    hub.register(node, channel)
    service.mark_online(node)
    try:
        await websocket.send_json(
            {
                "type": "hello_ack",
                "node_id": node.node_id,
                "server_time": datetime.now(UTC).isoformat(),
            }
        )
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                continue
            hub.handle_message(node, payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("Desktop node websocket failed node_id=%s", node.node_id, exc_info=True)
    finally:
        hub.unregister(node)
        try:
            service.mark_offline(node)
        except Exception:
            logger.warning("Failed to mark desktop node offline node_id=%s", node.node_id)
