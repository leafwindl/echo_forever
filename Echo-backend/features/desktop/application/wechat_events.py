"""微信消息事件 → Echo 回复 → 发回微信。"""

from __future__ import annotations

import asyncio
import json
import logging

from features.chat.public import generate_chat_reply
from features.desktop.application.desktop_service import DesktopService
from features.desktop.application.remote_command import run_remote_command

logger = logging.getLogger(__name__)

BRIDGE_SEND_TIMEOUT_SECONDS = 120

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


def _bridge_send_many_command(chat: str, texts: list[str]) -> str:
    body = json.dumps(
        {"chat": chat, "texts": texts},
        ensure_ascii=False,
    ).replace("'", "''")
    return (
        "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/send_many' -Method Post "
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
    result = await run_remote_command(
        service,
        user_id=user_id,
        command=command,
        owner_type="echo",
        timeout_seconds=timeout_seconds,
    )
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


async def handle_wechat_message(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    images: tuple[str, ...] = (),
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
        )


async def _handle_wechat_message_locked(
    *,
    service: DesktopService,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
    images: tuple[str, ...] = (),
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
        # 一次批量发送：bridge 复用常驻 WeChat 实例，避免每条消息都起新进程
        ok, detail = await _run_remote_command(
            service=service,
            user_id=user_id,
            command=_bridge_send_many_command(chat, list(segments)),
            timeout_seconds=BRIDGE_SEND_TIMEOUT_SECONDS,
        )
        if not ok:
            logger.warning(
                "wechat reply delivery failed local_id=%s detail=%s",
                local_id,
                detail[:200],
            )
            return
        logger.info(
            "wechat reply delivered local_id=%s segments=%s",
            local_id,
            len(segments),
        )
    except Exception:
        logger.warning("wechat event handling failed local_id=%s", local_id, exc_info=True)


__all__ = ["handle_wechat_message"]
