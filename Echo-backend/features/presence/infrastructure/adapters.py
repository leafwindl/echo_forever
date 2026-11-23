from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from features.presence.domain.entities import (
    PresenceActionSummary,
    PresenceContext,
    PresenceMemory,
    PresenceMessage,
)


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
            recent_actions=await self._recent_actions(user_id),
            recent_messages=tuple(messages[-3:]),
            open_goals=await self._open_goals(user_id),
            timezone=timezone,
        )

    async def _open_goals(self, user_id: str) -> tuple[str, ...]:
        from features.proactive_chat.public import pending_goal_summaries

        try:
            return tuple(
                await asyncio.to_thread(pending_goal_summaries, user_id, 3)
            )
        except Exception:
            return ()

    async def _recent_actions(self, user_id: str) -> tuple[PresenceActionSummary, ...]:
        from features.desktop.public import recent_bili_scan_summaries
        from features.proactive_chat.public import recent_goal_summaries

        summaries: list[PresenceActionSummary] = []
        for fetcher in (recent_goal_summaries, recent_bili_scan_summaries):
            try:
                rows = await asyncio.to_thread(fetcher, user_id, 3)
            except Exception:
                continue
            for row in rows:
                occurred_at = row.get("occurred_at")
                if occurred_at is None:
                    continue
                summaries.append(
                    PresenceActionSummary(
                        kind=str(row.get("kind") or ""),
                        summary=str(row.get("summary") or "")[:200],
                        occurred_at=occurred_at,
                    )
                )
        summaries.sort(key=lambda item: item.occurred_at, reverse=True)
        return tuple(summaries[:5])

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
        plan: str = "",
    ) -> str:
        from features.proactive_chat.public import create_proactive_goal

        return create_proactive_goal(
            user_id=user_id,
            intent=intent,
            draft_text=draft_text,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            action_intent=action_intent,
            plan=plan,
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
