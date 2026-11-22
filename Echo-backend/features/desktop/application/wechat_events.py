"""微信消息事件 → Echo 回复 → 发回微信。"""

from __future__ import annotations

import asyncio
import json
import logging

from features.chat.public import generate_chat_reply
from features.desktop.application.desktop_service import DesktopService
from features.desktop.domain.entities import DesktopError

logger = logging.getLogger(__name__)

BRIDGE_SEND_TIMEOUT_SECONDS = 120
SEGMENT_INTERVAL_SECONDS = 0.8

# 微信消息必须按顺序处理：并发会让多条回复交错、乱序
_WECHAT_TURN_LOCK = asyncio.Lock()


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _bridge_send_command(chat: str, text: str) -> str:
    body = json.dumps({"to": chat, "text": text}, ensure_ascii=False).replace("'", "''")
    return (
        "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/send' -Method Post "
        "-ContentType 'application/json; charset=utf-8' "
        f"-Body '{body}' -TimeoutSec 180 | ConvertTo-Json -Compress -Depth 6"
    )


async def _run_remote_command(
    *,
    service: DesktopService,
    user_id: str,
    command: str,
    timeout_seconds: int = BRIDGE_SEND_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    try:
        start = await service.execute(
            user_id=user_id,
            action="exec",
            arguments={"command": command},
            timeout_seconds=30,
            owner_type="echo",
        )
    except DesktopError as exc:
        return False, exc.message
    job_id = start.data.get("job_id")
    if job_id is None:
        return True, str(start.data.get("output") or "")
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(2)
        try:
            result = await service.execute(
                user_id=user_id,
                action="job_result",
                arguments={"job_id": job_id},
                timeout_seconds=20,
                owner_type="echo",
            )
        except DesktopError as exc:
            return False, exc.message
        status = str(result.data.get("status") or "")
        if status == "done":
            return True, str(result.data.get("output") or "")
        if status in {"failed", "missing"}:
            return False, str(result.data.get("output") or status)
    return False, "timeout"


async def send_wechat_text(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    text: str,
) -> bool:
    """把一段文本通过微信桥发出去（Echo 主动发消息用）。"""
    ok, _detail = await _run_remote_command(
        service=service,
        user_id=user_id,
        command=_bridge_send_command(chat, text),
    )
    return ok


async def handle_wechat_message(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    image_base64: str = "",
    image_hash: str = "",
    image_description: str = "",
) -> None:
    """把微信新消息交给 Echo，回复按回复分段逐条发回微信。

    全局串行：同一时间只处理一条微信消息，避免回复交错乱序。
    """
    async with _WECHAT_TURN_LOCK:
        await _handle_wechat_message_locked(
            service=service,
            user_id=user_id,
            chat=chat,
            content=content,
            local_id=local_id,
            image_base64=image_base64,
            image_hash=image_hash,
            image_description=image_description,
        )


async def _handle_wechat_message_locked(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    image_base64: str = "",
    image_hash: str = "",
    image_description: str = "",
) -> None:
    try:
        message_text = f"（微信）{chat} 对你说：{content}"
        if image_base64:
            if image_description:
                message_text = (
                    f"（微信）{chat} 给你发了一张图片，图片内容是：{image_description}"
                )
            else:
                message_text = f"（微信）{chat} 给你发了一张图片（识别失败）。"
            logger.info(
                "wechat image received local_id=%s hash=%s desc_len=%s",
                local_id,
                image_hash,
                len(image_description),
            )
        result = await generate_chat_reply(
            user_id,
            message=message_text,
            conversation_mode="chat",
        )
        segments = tuple(
            segment.strip() for segment in result.reply_segments if segment.strip()
        )
        if not segments:
            fallback = (result.reply or "").strip()
            segments = (fallback,) if fallback else ()
        if not segments:
            logger.info("wechat event produced empty reply local_id=%s", local_id)
            return
        for index, segment in enumerate(segments):
            ok, detail = await _run_remote_command(
                service=service,
                user_id=user_id,
                command=_bridge_send_command(chat, segment),
            )
            if not ok:
                logger.warning(
                    "wechat reply delivery failed local_id=%s segment=%s detail=%s",
                    local_id,
                    index,
                    detail[:200],
                )
                break
            if index < len(segments) - 1:
                await asyncio.sleep(SEGMENT_INTERVAL_SECONDS)
        logger.info(
            "wechat reply delivered local_id=%s segments=%s",
            local_id,
            len(segments),
        )
    except Exception:
        logger.warning("wechat event handling failed local_id=%s", local_id, exc_info=True)


__all__ = ["handle_wechat_message"]
