from __future__ import annotations

import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from features.presence.domain.entities import (
    PresenceContext,
    PresenceMemory,
    PresenceMessage,
)

# Echo 在虚拟机小号上看到的主号联系人名
_WECHAT_NOTIFY_TARGET = "叶子"


class ChatPresenceContextSource:
    async def load(self, user_id: str, limit: int) -> PresenceContext:
        from features.chat.public import list_chat_messages
        from features.proactive_chat.public import get_proactive_preferences

        timezone = get_proactive_preferences(user_id).timezone or "Asia/Shanghai"
        page = await asyncio.to_thread(
            list_chat_messages,
            user_id,
            None,
            None,
            max(limit, 30),
        )
        messages = tuple(
            PresenceMessage(role=item.role, content=item.content, created_at=item.created_at)
            for item in page.items
            if item.role in {"user", "assistant"} and item.content.strip()
        )
        user_messages = [item for item in messages if item.role == "user"]
        assistant_messages = [item for item in messages if item.role == "assistant"]
        last_user = max(user_messages, key=lambda item: item.created_at, default=None)
        last_assistant = max(assistant_messages, key=lambda item: item.created_at, default=None)
        return PresenceContext(
            messages=messages,
            last_user_message_at=last_user.created_at if last_user else None,
            last_user_text=" ".join(last_user.content.split())[:300] if last_user else "",
            recent_assistant_text=(
                " ".join(last_assistant.content.split())[:300] if last_assistant else ""
            ),
            last_assistant_at=last_assistant.created_at if last_assistant else None,
            timezone=timezone,
        )

    def recent_user_ids(self, limit: int) -> tuple[str, ...]:
        from features.chat.public import list_recent_chat_user_ids

        return list_recent_chat_user_ids(limit)


class MemoryPresenceSource:
    async def recall(self, user_id: str, query: str) -> PresenceMemory | None:
        from features.memory.public import recall_memory

        hits = await recall_memory(user_id, query, limit=1)
        if not hits:
            return None
        hit = hits[0]
        return PresenceMemory(
            memory_id=hit.memory_id,
            content=hit.content,
            importance=hit.importance,
        )


class DesktopPresenceActionExecutor:
    async def execute(
        self,
        *,
        user_id: str,
        action_intent: str,
        thought_id: str,
    ) -> str:
        from features.desktop.public import DesktopError, execute_desktop_action

        _ = thought_id
        kind, _, argument = action_intent.partition(":")
        kind = kind.strip().lower()
        argument = argument.strip()
        if not argument:
            return ""
        if kind == "music":
            action = "music_search_play"
            arguments = {"query": argument[:160]}
            timeout = 65
        elif kind == "notepad":
            action = "notepad_write"
            arguments = {"text": argument[:2000]}
            timeout = 45
        elif kind == "dsh":
            action = "dsh_task"
            arguments = {"instruction": argument[:2000], "workspace": ""}
            timeout = 300
        elif kind == "wechat":
            body = json.dumps(
                {"to": _WECHAT_NOTIFY_TARGET, "text": argument[:2000]},
                ensure_ascii=False,
            ).replace("'", "''")
            action = "exec"
            arguments = {
                "command": (
                    "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/send' -Method Post "
                    "-ContentType 'application/json; charset=utf-8' "
                    f"-Body '{body}' -TimeoutSec 180 | ConvertTo-Json -Compress -Depth 6"
                )
            }
            timeout = 200
        else:
            return ""
        owner_type = "echo" if kind == "wechat" else "user"
        try:
            result = await execute_desktop_action(
                user_id=user_id,
                action=action,
                arguments=arguments,
                timeout_seconds=timeout,
                owner_type=owner_type,
            )
        except DesktopError:
            return ""
        return str(result.data.get("result") or result.data.get("preview") or "ok")


class MemoryPresenceWriter:
    async def remember(self, *, user_id: str, text: str, salience: float) -> str | None:
        from features.memory.public import remember_presence_thought

        return await remember_presence_thought(
            user_id,
            content=text,
            salience=salience,
        )


class ProactivePresenceGoalCreator:
    """把念头交给统一投递通道：投递本身由 proactive job worker 负责。"""

    def create_goal(
        self,
        *,
        user_id: str,
        intent: str,
        draft_text: str,
        trigger_type: str = "presence",
        trigger_ref: str = "",
        action_intent: str = "",
    ) -> str:
        from features.proactive_chat.public import create_proactive_goal

        return create_proactive_goal(
            user_id=user_id,
            intent=intent,
            draft_text=draft_text,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            action_intent=action_intent,
        )


class ProactiveQuietHours:
    def is_quiet(self, user_id: str, now: datetime) -> bool:
        from features.proactive_chat.public import get_proactive_preferences

        preference = get_proactive_preferences(user_id)
        local = now.astimezone(ZoneInfo(preference.timezone)).time()
        start, end = preference.quiet_start, preference.quiet_end
        if start == end:
            return False
        return start <= local < end if start < end else local >= start or local < end

    def can_send_spontaneous(self, user_id: str, now: datetime) -> bool:
        from features.proactive_chat.public import get_proactive_preferences

        preference = get_proactive_preferences(user_id)
        if not preference.enabled or not preference.allow_spontaneous_chat:
            return False
        if preference.pause_indefinite:
            return False
        return preference.paused_until is None or preference.paused_until <= now
