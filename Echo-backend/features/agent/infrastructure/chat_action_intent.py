"""用一次轻量模型调用判断聊天轮的行动意图。

正则负责高置信的明确指令和明确否定；这里只处理正则没抓住的模糊句
（指代、省略宾语，比如「你去刷吧」）。
"""

from __future__ import annotations

import json
import logging

from features.agent.domain.chat_action_routing import (
    ChatActionMode,
    ChatActionRoute,
    explicit_route,
    suggest_route,
)

logger = logging.getLogger(__name__)

INTENT_PROMPT = (
    "你是 Echo 的意图识别器。判断用户这句话是不是在让 Echo 去刷B站/看视频。"
    "只输出一个 JSON 对象，不要 Markdown："
    '{"mode": "explicit|suggest|none", "reason": "20字以内"}'
    "explicit：明确让 Echo 去刷/看/找视频，祈使语气、省略宾语也算（如“你去刷吧”）。"
    "suggest：给了行动的余地但没有直接命令（如“好无聊”“随便看看”）。"
    "none：闲聊、否定（如“别刷了”），或与刷B站无关。"
)


def _parse(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


async def classify_chat_action(message: str) -> ChatActionRoute:
    """模型判定；失败时返回 NONE，不影响主流程。"""
    from providers.llm_provider import get_llm_provider

    try:
        response = await get_llm_provider().chat_completion_message(
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": message[:500]},
            ],
            thinking={"type": "disabled"},
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        payload = _parse(response.content)
    except Exception:
        logger.warning("chat action intent failed", exc_info=True)
        return ChatActionRoute()
    mode = str(payload.get("mode") or "").strip().lower()
    reason = " ".join(str(payload.get("reason") or "").split())[:40]
    logger.info("chat action intent mode=%s reason=%s", mode or "none", reason)
    if mode == ChatActionMode.EXPLICIT.value:
        return explicit_route()
    if mode == ChatActionMode.SUGGEST.value:
        return suggest_route()
    return ChatActionRoute()
