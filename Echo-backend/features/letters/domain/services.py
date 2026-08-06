from __future__ import annotations

from typing import Protocol


class LetterLanguageModel(Protocol):
    """Domain-facing contract used to compose a daily letter."""

    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...
