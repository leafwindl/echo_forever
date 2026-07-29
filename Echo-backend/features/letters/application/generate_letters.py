from __future__ import annotations

import logging
from datetime import datetime, timezone

from features.letters.domain.repositories import LetterRepository
from providers.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class GenerateDueLetters:
    def __init__(self, repository: LetterRepository, llm: LLMProvider):
        self.repository = repository
        self.llm = llm

    async def execute(self) -> int:
        created = 0
        for user_id, preference, local_date in self.repository.due_users(
            datetime.now(timezone.utc)
        ):
            if self.repository.exists(user_id, local_date):
                continue
            messages = self.repository.source_messages(user_id, local_date, preference.timezone)
            user_messages = [row for row in messages if row["role"] == "user"]
            if not user_messages:
                self.repository.create_skipped(user_id, local_date, preference.timezone)
                continue
            transcript = "\n".join(
                f"{row['role']}: {row['content']}" for row in messages
            )[:12000]
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "你是 Echo。根据昨天真实发生的对话写一封150到500中文字的信。"
                        "不是流水账摘要，要温暖但不过度亲密，表达有限而真实的观察。"
                        "不得虚构离线经历、身体活动、环境或用户未说过的事实。"
                        "首行只写主题，随后空一行写正文；不要要求用户回复。"
                    ),
                },
                {"role": "user", "content": transcript},
            ]
            try:
                raw = (
                    await self.llm.chat_completion(prompt, temperature=0.7, max_tokens=900)
                ).strip()
                lines = raw.splitlines()
                subject = lines[0].lstrip("# ").strip()[:120] or "写给你的今天"
                content = "\n".join(lines[1:]).strip() or raw
                if self.repository.create_ready(
                    user_id,
                    local_date,
                    preference.timezone,
                    subject,
                    content,
                    [int(row["id"]) for row in messages],
                ):
                    created += 1
            except Exception:
                logger.warning("Daily letter generation failed user_id=%s", user_id, exc_info=True)
        return created
