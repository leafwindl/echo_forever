from __future__ import annotations

import logging
import threading
import time
from typing import Any

from features.chat.domain.entities import CHAT_CHANNEL_WECHAT, CHAT_VISIBILITY_WECHAT
from features.chat.public import generate_chat_reply
from features.mobile_agent.application.skills import run_app_skill

logger = logging.getLogger(__name__)

ALLOWED_WECHAT_CONTACT = "叶子"
_DEDUPE_TTL_SECONDS = 600
_dedupe_lock = threading.Lock()
_recent_message_keys: dict[str, float] = {}


class WechatChannelError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _claim_message_key(user_id: str, device_id: str, message_id: str) -> bool:
    key = f"{user_id}:{device_id}:{message_id}"
    now = time.monotonic()
    with _dedupe_lock:
        stale = [
            item
            for item, claimed_at in _recent_message_keys.items()
            if now - claimed_at > _DEDUPE_TTL_SECONDS
        ]
        for item in stale:
            _recent_message_keys.pop(item, None)
        if key in _recent_message_keys:
            return False
        _recent_message_keys[key] = now
        return True


async def handle_wechat_inbound(
    *,
    user_id: str,
    device_id: str,
    contact: str,
    text: str,
    message_id: str,
) -> dict[str, Any]:
    clean_contact = contact.strip()
    clean_text = text.strip()
    clean_message_id = message_id.strip()
    if clean_contact != ALLOWED_WECHAT_CONTACT:
        raise WechatChannelError("contact_not_allowed", "只接受联系人“叶子”")
    if not clean_text or len(clean_text) > 500:
        raise WechatChannelError("invalid_message", "消息内容不能为空且不能超过 500 字")
    if not clean_message_id or len(clean_message_id) > 300:
        raise WechatChannelError("invalid_message_id", "缺少微信消息标识")
    if not _claim_message_key(user_id, device_id, clean_message_id):
        return {"duplicate": True, "replied": False}

    turn = await generate_chat_reply(
        user_id,
        clean_text,
        message_channel=CHAT_CHANNEL_WECHAT,
        message_visibility=CHAT_VISIBILITY_WECHAT,
    )
    reply = turn.reply.strip()
    segments = [
        segment.strip()
        for segment in turn.reply_segments
        if segment and segment.strip()
    ]
    if not segments and reply:
        segments = [reply]
    if not reply or not segments:
        return {
            "duplicate": False,
            "replied": False,
            "reason": "empty_reply",
            "conversation_id": turn.conversation_id,
        }
    try:
        sent = await run_app_skill(
            user_id=user_id,
            skill="wechat",
            action="send_segments",
            parameters={"texts": segments},
            device_id=device_id,
        )
    except Exception:
        logger.exception(
            "WeChat reply delivery failed user_id=%s device_id=%s",
            user_id,
            device_id,
        )
        return {
            "duplicate": False,
            "replied": False,
            "reason": "send_failed",
            "reply": reply,
            "segments": segments,
            "conversation_id": turn.conversation_id,
        }
    return {
        "duplicate": False,
        "replied": bool(sent.data.get("sent")),
        "reply": reply,
        "segments": segments,
        "sent_segments": int(sent.data.get("sent_segments") or 0),
        "conversation_id": turn.conversation_id,
    }
