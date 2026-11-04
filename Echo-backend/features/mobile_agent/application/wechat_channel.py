from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from difflib import SequenceMatcher
from typing import Any

from features.chat.domain.entities import CHAT_CHANNEL_WECHAT, CHAT_VISIBILITY_WECHAT
from features.chat.public import (
    generate_chat_reply,
    list_recent_assistant_contents_for_guard,
)
from features.mobile_agent.application.skills import run_app_skill

logger = logging.getLogger(__name__)

ALLOWED_WECHAT_CONTACT = "叶子"
_DEDUPE_TTL_SECONDS = 600
_dedupe_lock = threading.Lock()
_recent_message_keys: dict[str, float] = {}
_INBOUND_WINDOW_SECONDS = 60
_MAX_INBOUND_PER_WINDOW = 6
_recent_inbound: dict[str, deque[float]] = {}


class WechatChannelError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_for_loop_guard(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.lower())


def _edit_distance(left: str, right: str) -> int:
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row_index, right_char in enumerate(right, start=1):
        current = [row_index]
        for column_index, left_char in enumerate(left, start=1):
            insert = current[column_index - 1] + 1
            delete = previous[column_index] + 1
            replace = previous[column_index - 1] + (left_char != right_char)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def _looks_like_echo_loop(user_id: str, text: str) -> bool:
    normalized = _normalize_for_loop_guard(text)
    if len(normalized) < 6:
        return False
    recent_replies = list_recent_assistant_contents_for_guard(user_id, limit=24)
    for reply in recent_replies:
        candidate = _normalize_for_loop_guard(reply)
        if not candidate:
            continue
        if normalized in candidate:
            return True
        smallest = max(6, int(len(normalized) * 0.5))
        if smallest > len(candidate):
            continue
        matcher = SequenceMatcher(
            None,
            normalized,
            candidate,
            autojunk=False,
        )
        match = matcher.find_longest_match(0, len(normalized), 0, len(candidate))
        if match.size >= smallest or matcher.ratio() >= 0.6:
            return True
        window = candidate[: len(normalized)]
        if _edit_distance(normalized, window) <= max(3, len(normalized) // 5):
            return True
    return False


def _allow_inbound(user_id: str, device_id: str) -> bool:
    key = f"{user_id}:{device_id}"
    now = time.monotonic()
    with _dedupe_lock:
        window = _recent_inbound.setdefault(key, deque())
        while window and now - window[0] > _INBOUND_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= _MAX_INBOUND_PER_WINDOW:
            return False
        window.append(now)
        return True


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
    if _looks_like_echo_loop(user_id, clean_text):
        logger.warning(
            "Rejected WeChat inbound that matches a recent Echo reply user_id=%s device_id=%s",
            user_id,
            device_id,
        )
        return {
            "duplicate": True,
            "replied": False,
            "reason": "echo_loop",
        }
    if not _allow_inbound(user_id, device_id):
        logger.warning(
            "WeChat inbound circuit breaker tripped user_id=%s device_id=%s",
            user_id,
            device_id,
        )
        return {
            "duplicate": False,
            "replied": False,
            "reason": "rate_limited",
        }
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
