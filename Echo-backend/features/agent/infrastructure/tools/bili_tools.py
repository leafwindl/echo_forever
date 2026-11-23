"""B站能力：看推荐流和分享给叶子，拆成两个独立工具。

- `bili_browse`：只刷、只列标题，帧留在 Echo 自己的电脑上，不把图塞进模型上下文。
- `bili_share`：选中一帧，发微信、传 COS、写聊天历史。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time

from pydantic import BaseModel, Field

from features.agent.domain.entities import AgentToolResult, AgentToolStatus, ToolSpecification
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.desktop.public import run_desktop_command

logger = logging.getLogger(__name__)

BILI_SCAN_COMMAND = (
    "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/bili_scan' -Method Post "
    "-ContentType 'application/json; charset=utf-8' -TimeoutSec 420 "
    "| ConvertTo-Json -Compress -Depth 6"
)


def _bridge_command(path: str, payload: dict, *, timeout_seconds: int) -> str:
    body = json.dumps(payload, ensure_ascii=False).replace("'", "''")
    return (
        f"Invoke-RestMethod -Uri 'http://127.0.0.1:8765{path}' -Method Post "
        "-ContentType 'application/json; charset=utf-8' "
        f"-Body '{body}' -TimeoutSec {timeout_seconds} | ConvertTo-Json -Compress -Depth 6"
    )


def _failed(tool_name: str, code: str, message: str) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.FAILED,
        error_code=code,
        safe_for_model=message,
    )


def _completed(
    tool_name: str,
    *,
    safe_for_model: str,
    data: dict | None = None,
) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.COMPLETED,
        data=data or {},
        safe_for_model=safe_for_model,
    )


class BiliBrowseArguments(BaseModel):
    limit: int = Field(default=8, ge=1, le=10, description="返回个数")


class BiliShareArguments(BaseModel):
    frame: str = Field(
        min_length=1,
        max_length=200,
        description="帧文件名",
    )
    title: str = Field(default="", max_length=120, description="标题")
    note: str = Field(min_length=1, max_length=200, description="发给叶子的话术")


def _store_frame(image_base64: str) -> str:
    """帧存 COS，历史里可以回看；失败只少图。"""
    if not image_base64:
        return ""
    try:
        from shared.storage.cos_storage import get_cos_object_storage

        data = base64.b64decode(image_base64)
        digest = hashlib.md5(data).hexdigest()[:12]
        key = f"bili/{int(time.time())}_{digest}.png"
        storage = get_cos_object_storage()
        storage.put_bytes(key, data, "image/png", cache_control="private, max-age=604800")
        return storage.download_url(key, expires_seconds=86400)
    except Exception:
        logger.warning("store bili frame failed in tool", exc_info=True)
        return ""


async def _browse(context: ToolExecutionContext, parsed: BiliBrowseArguments) -> AgentToolResult:
    result = await run_desktop_command(
        user_id=context.user_id,
        command=BILI_SCAN_COMMAND,
        owner_type="echo",
        timeout_seconds=480,
    )
    if not result.ok:
        return _failed("bili_browse", "scan_failed", result.output[:300] or "B站扫描失败")
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        return _failed("bili_browse", "scan_non_json", "B站扫描返回的不是 JSON")
    items: list[dict[str, str]] = []
    for item in payload.get("items") or []:
        if not item.get("ok") or not item.get("frame"):
            continue
        name = str(item.get("frame") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not name:
            continue
        items.append({"frame": name, "title": str(item.get("title") or "")[:80]})
        if len(items) >= parsed.limit:
            break
    if not items:
        return _completed(
            "bili_browse",
            safe_for_model="这轮没刷到可分享的视频。",
            data={"items": []},
        )
    listing = "\n".join(
        f"- {index + 1}. {item['title']}（frame: {item['frame']}）"
        for index, item in enumerate(items)
    )
    return _completed(
        "bili_browse",
        safe_for_model=f"刷到这些视频，图还在你自己的电脑上：\n{listing}",
        data={"items": items},
    )


async def _share(context: ToolExecutionContext, parsed: BiliShareArguments) -> AgentToolResult:
    frame = parsed.frame
    # 1. 先真正发给叶子
    send_result = await run_desktop_command(
        user_id=context.user_id,
        command=_bridge_command(
            "/send_image",
            {"path": frame, "text": parsed.note},
            timeout_seconds=120,
        ),
        owner_type="echo",
        timeout_seconds=140,
    )
    if not send_result.ok:
        return _failed("bili_share", "send_failed", send_result.output[:300])
    try:
        sent = json.loads(send_result.output)
    except json.JSONDecodeError:
        sent = {}
    if not isinstance(sent, dict) or not sent.get("ok"):
        return _failed("bili_share", "bridge_rejected", str(sent)[:300] or "bridge 拒绝发送")

    # 2. 取帧存 COS，再写进聊天历史（失败只少图，不影响已发送的事实）
    image_url = ""
    try:
        frame_result = await run_desktop_command(
            user_id=context.user_id,
            command=_bridge_command("/frame", {"name": frame}, timeout_seconds=60),
            owner_type="echo",
            timeout_seconds=80,
        )
        if frame_result.ok:
            frame_payload = json.loads(frame_result.output)
            image_url = _store_frame(str(frame_payload.get("image_base64") or ""))
    except Exception:
        logger.warning("bili share frame store failed", exc_info=True)

    title = parsed.title.strip() or frame
    try:
        from features.agent.domain.entities import ContentPart
        from features.chat.public import deliver_external_assistant_message

        content_parts = ((ContentPart(type="image", url=image_url),) if image_url else ())
        await deliver_external_assistant_message(
            user_id=context.user_id,
            content=f"刚刷到一个视频《{title}》，觉得挺有意思，分享给你了。",
            idempotency_key=f"bili_share:{frame}:{parsed.note[:24]}",
            source="bili",
            content_parts=content_parts,
        )
    except Exception:
        logger.warning("bili share history failed", exc_info=True)

    return _completed(
        "bili_share",
        safe_for_model=f"已经把《{title}》发给叶子了。",
        data={"title": title, "frame": frame},
    )


def register_bili_tools(registry: ToolRegistry) -> None:
    async def browse_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = BiliBrowseArguments.model_validate(arguments)
        return await _browse(context, parsed)

    async def share_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = BiliShareArguments.model_validate(arguments)
        return await _share(context, parsed)

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="bili_browse",
                description="刷B站推荐流，返回标题和帧名，不自动发送。",
                timeout_seconds=170,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=1,
                max_successful_calls_per_turn=1,
            ),
            arguments_model=BiliBrowseArguments,
            handler=browse_handler,
        )
    )
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="bili_share",
                description="把选中的视频连图带话术发给叶子。",
                timeout_seconds=90,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=2,
                max_successful_calls_per_turn=2,
            ),
            arguments_model=BiliShareArguments,
            handler=share_handler,
        )
    )


__all__ = ["register_bili_tools"]
