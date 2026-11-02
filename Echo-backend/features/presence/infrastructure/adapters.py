from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from features.presence.domain.entities import (
    PresenceContext,
    PresenceMemory,
    PresenceMessage,
)


class ChatPresenceContextSource:
    async def load(self, user_id: str, limit: int) -> PresenceContext:
        from features.chat.public import list_chat_messages

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
        else:
            return ""
        try:
            result = await execute_desktop_action(
                user_id=user_id,
                action=action,
                arguments=arguments,
                timeout_seconds=timeout,
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


class ChatPresenceMessageDelivery:
    async def deliver(self, *, user_id: str, thought_id: str, text: str) -> bool:
        from features.chat.public import deliver_external_assistant_message

        await deliver_external_assistant_message(
            user_id=user_id,
            content=text,
            idempotency_key=f"presence:{thought_id}",
            source="presence",
        )
        return True


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
