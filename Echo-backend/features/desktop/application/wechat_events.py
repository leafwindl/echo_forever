"""微信消息事件 → Echo 回复 → 发回微信。"""

from __future__ import annotations

import asyncio
import json
import logging

from features.chat.public import send_chat_message
from features.desktop.application.desktop_service import get_desktop_service
from features.desktop.domain.entities import DesktopError

logger = logging.getLogger(__name__)

BRIDGE_SEND_TIMEOUT_SECONDS = 120


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
    user_id: str,
    command: str,
    timeout_seconds: int = BRIDGE_SEND_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    service = get_desktop_service()
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


async def handle_wechat_message(
    *,
    user_id: str,
    chat: str,
    content: str,
    local_id: int,
) -> None:
    """把微信新消息交给 Echo，回复再发回微信。"""
    try:
        result = await send_chat_message(
            user_id,
            message=f"（微信）{chat} 对你说：{content}",
            conversation_mode="chat",
            synthesize_voice=False,
        )
        reply = (result.reply or "").strip()
        if not reply:
            logger.info("wechat event produced empty reply local_id=%s", local_id)
            return
        ok, detail = await _run_remote_command(
            user_id=user_id,
            command=_bridge_send_command(chat, reply),
        )
        if ok:
            logger.info("wechat reply delivered local_id=%s", local_id)
        else:
            logger.warning(
                "wechat reply delivery failed local_id=%s detail=%s",
                local_id,
                detail[:200],
            )
    except Exception:
        logger.warning("wechat event handling failed local_id=%s", local_id, exc_info=True)


__all__ = ["handle_wechat_message"]
