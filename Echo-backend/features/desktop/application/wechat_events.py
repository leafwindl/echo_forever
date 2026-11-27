"""微信消息事件 → Echo 回复 → 发回微信（文字 + 表情包图片）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from urllib.parse import urlsplit

from features.chat.public import (
    CHAT_CHANNEL_WECHAT,
    DeliveryItem,
    build_chat_delivery_items,
    generate_chat_reply,
)
from features.desktop.application.desktop_service import DesktopService
from features.desktop.application.remote_command import run_remote_command

logger = logging.getLogger(__name__)

BRIDGE_SEND_TIMEOUT_SECONDS = 120
STICKER_DOWNLOAD_TIMEOUT_SECONDS = 60
STICKER_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
# 与 wechat_bridge.py 的 IMAGE_OUT_DIR 保持一致；bridge 只接受该目录下的文件名
VM_IMAGE_DIR = "C:\\EchoComputer\\images"

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


def _bridge_send_sequence_command(items: list[dict]) -> str:
    body = json.dumps({"items": items}, ensure_ascii=False).replace("'", "''")
    return (
        "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/send_sequence' -Method Post "
        "-ContentType 'application/json; charset=utf-8' "
        f"-Body '{body}' -TimeoutSec 180 | ConvertTo-Json -Compress -Depth 6"
    )


def _sticker_suffix(url: str) -> str:
    path = urlsplit(url).path
    dot = path.rfind(".")
    return path[dot:].lower() if dot >= 0 else ""


def _sticker_filename(sticker_id: str, url: str) -> str:
    """ASCII 文件名；同一张图命中 VM 本地缓存，不再重复下载。"""
    seed = sticker_id.strip() or url.strip()
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"stk_{digest}{_sticker_suffix(url)}"


def _sticker_download_command(url: str, filename: str) -> str:
    target = f"{VM_IMAGE_DIR}\\{filename}"
    # Stop 让下载失败变成 job failed，避免“命令成功但文件不存在”的假成功。
    return (
        "$ErrorActionPreference='Stop';"
        f"$p='{_ps_quote(target)}';"
        "if (-not (Test-Path -LiteralPath $p)) {"
        f"Invoke-WebRequest -Uri '{_ps_quote(url)}' -OutFile $p "
        "-UseBasicParsing -TimeoutSec 60"
        "};"
        "(Get-Item -LiteralPath $p).Length"
    )


async def _run_remote_command(
    *,
    service: DesktopService,
    user_id: str,
    command: str,
    timeout_seconds: int = BRIDGE_SEND_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """发送失败且节点刚掉线时重试几次，覆盖 agent 重连窗口。"""
    result = None
    for attempt in range(3):
        result = await run_remote_command(
            service,
            user_id=user_id,
            command=command,
            owner_type="echo",
            timeout_seconds=timeout_seconds,
        )
        if result.ok or result.status != "desktop_offline":
            return result.ok, result.output
        if attempt < 2:
            await asyncio.sleep(3)
    if result is None:
        return False, "desktop_offline"
    return result.ok, result.output


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


async def _prepare_sticker_file(
    *,
    service: DesktopService,
    user_id: str,
    part,
) -> str:
    """确保贴纸图片在 VM 的 images 目录里，返回 bridge 可用的文件名。"""
    url = part.url.strip()
    if not url:
        return ""
    suffix = _sticker_suffix(url)
    if suffix not in STICKER_IMAGE_SUFFIXES:
        logger.info(
            "wechat sticker skipped sticker_id=%s suffix=%s",
            part.sticker_id,
            suffix or "none",
        )
        return ""
    filename = _sticker_filename(part.sticker_id, url)
    ok, output = await _run_remote_command(
        service=service,
        user_id=user_id,
        command=_sticker_download_command(url, filename),
        timeout_seconds=STICKER_DOWNLOAD_TIMEOUT_SECONDS,
    )
    if not ok:
        logger.warning(
            "wechat sticker download failed sticker_id=%s detail=%s",
            part.sticker_id,
            output[:200],
        )
        return ""
    return filename


async def send_wechat_delivery(
    *,
    service: DesktopService,
    user_id: str,
    items: tuple[DeliveryItem, ...],
) -> bool:
    """按交付顺序发文字和贴纸图片；图片失败只降级为文字，不伪造成功。

    微信桥固定在唯一联系人窗口发送，所以不需要再传 chat。
    和 APP 的 firstSticker 一致：一轮回复只发第一张贴纸。
    """
    payload_items: list[dict] = []
    sticker_handled = False
    for item in items:
        if item.message_type == "text":
            text = item.content.strip()
            if text:
                payload_items.append({"type": "text", "text": text})
            continue
        if item.message_type != "sticker" or not item.parts:
            continue
        if sticker_handled:
            continue
        part = item.parts[0]
        if part.type != "sticker":
            continue
        sticker_handled = True
        filename = await _prepare_sticker_file(
            service=service,
            user_id=user_id,
            part=part,
        )
        if filename:
            payload_items.append({"type": "image", "path": filename})

    if not payload_items:
        logger.info("wechat delivery has no deliverable items")
        return False

    ok, output = await _run_remote_command(
        service=service,
        user_id=user_id,
        command=_bridge_send_sequence_command(payload_items),
    )
    if not ok:
        logger.warning("wechat delivery failed detail=%s", output[:300])
        return False
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict) or not payload.get("ok"):
        logger.warning("wechat bridge rejected delivery: %s", str(payload)[:300])
        return False
    logger.info("wechat delivery sent items=%s", len(payload_items))
    return True


async def handle_wechat_message(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    images: tuple[str, ...] = (),
    source_created_at: datetime | None = None,
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
            images=images,
            source_created_at=source_created_at,
        )


async def _handle_wechat_message_locked(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    images: tuple[str, ...] = (),
    source_created_at: datetime | None = None,
) -> None:
    try:
        message_text = f"（微信）{chat} 对你说：{content}"
        if images:
            if content.strip() and content.strip() != "[图片]":
                message_text = f"（微信）{chat} 给你发来图片，并说：{content}"
            else:
                message_text = f"（微信）{chat} 给你发来图片"
            logger.info(
                "wechat message with images local_id=%s images=%s",
                local_id,
                len(images),
            )
        result = await generate_chat_reply(
            user_id,
            message=message_text,
            conversation_mode="chat",
            user_images=images,
            message_channel=CHAT_CHANNEL_WECHAT,
            source_created_at=source_created_at,
        )
        segments = tuple(
            segment.strip() for segment in result.reply_segments if segment.strip()
        )
        if not segments:
            fallback = (result.reply or "").strip()
            segments = (fallback,) if fallback else ()
        delivery_items = build_chat_delivery_items(
            segments,
            result.content_parts,
            result.sticker_placement,
        )
        if not delivery_items:
            logger.info("wechat event produced empty reply local_id=%s", local_id)
            return
        ok = await send_wechat_delivery(
            service=service,
            user_id=user_id,
            items=delivery_items,
        )
        if not ok:
            logger.warning("wechat reply delivery failed local_id=%s", local_id)
            return
        logger.info(
            "wechat reply delivered local_id=%s items=%s stickers=%s",
            local_id,
            len(delivery_items),
            sum(1 for item in delivery_items if item.message_type == "sticker"),
        )
    except Exception:
        logger.warning("wechat event handling failed local_id=%s", local_id, exc_info=True)


__all__ = ["handle_wechat_message", "send_wechat_delivery"]
