from __future__ import annotations

from collections.abc import Awaitable, Callable

_HARD_ENDINGS = frozenset(".!?") | frozenset("\u3002\uff01\uff1f")
_SOFT_ENDINGS = frozenset(",;:") | frozenset("\uff0c\uff1b\uff1a\u3001")


class CallReplyStreamLimiter:
    """Keep streamed Call delivery short and identical to persisted text."""

    def __init__(
        self,
        *,
        max_chars: int,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ):
        if max_chars < 8:
            raise ValueError("Call reply maximum is too small")
        self.max_chars = max_chars
        self.on_text_delta = on_text_delta
        self._pending = ""
        self._parts: list[str] = []
        self._delivered_chars = 0
        self._observed_chars = 0
        self._saw_delta = False
        self._closed = False
        self.truncated = False

    @property
    def text(self) -> str:
        return "".join(self._parts).strip()

    @property
    def observed_chars(self) -> int:
        return self._observed_chars

    async def push(self, delta: str) -> None:
        if not delta:
            return
        self._saw_delta = True
        self._observed_chars += len(delta)
        if self._closed:
            self.truncated = True
            return
        self._pending += delta
        await self._drain_complete_sentences()

    async def finish(self, fallback_text: str = "") -> str:
        if not self._saw_delta and fallback_text:
            self._pending = fallback_text
            self._observed_chars = len(fallback_text)
        if self._closed:
            return self.text

        await self._drain_complete_sentences()
        if self._closed:
            return self.text

        remaining = self._pending.strip()
        self._pending = ""
        if not remaining:
            self._closed = True
            return self.text

        remaining_budget = self.max_chars - self._delivered_chars
        if len(remaining) <= remaining_budget:
            await self._emit(remaining)
        elif self._parts:
            self.truncated = True
        else:
            self.truncated = True
            shortened = _shorten_first_utterance(remaining, self.max_chars)
            if shortened:
                await self._emit(shortened)
        self._closed = True
        return self.text

    async def _drain_complete_sentences(self) -> None:
        while self._pending and not self._closed:
            boundary = _first_sentence_boundary(self._pending)
            if boundary is None:
                return
            sentence = self._pending[:boundary].strip()
            self._pending = self._pending[boundary:]
            if not sentence:
                continue
            remaining_budget = self.max_chars - self._delivered_chars
            if len(sentence) <= remaining_budget:
                await self._emit(sentence)
                continue
            self.truncated = True
            if not self._parts:
                shortened = _shorten_first_utterance(sentence, self.max_chars)
                if shortened:
                    await self._emit(shortened)
            self._pending = ""
            self._closed = True

    async def _emit(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            return
        self._parts.append(clean)
        self._delivered_chars += len(clean)
        if self.on_text_delta is not None:
            await self.on_text_delta(clean)


def limit_call_reply(text: str, max_chars: int) -> str:
    """Apply the same deterministic limit when the model cannot stream."""

    clean = text.strip()
    if len(clean) <= max_chars:
        return clean

    result: list[str] = []
    delivered_chars = 0
    pending = clean
    while pending:
        boundary = _first_sentence_boundary(pending)
        if boundary is None:
            break
        sentence = pending[:boundary].strip()
        pending = pending[boundary:]
        if not sentence:
            continue
        if delivered_chars + len(sentence) > max_chars:
            break
        result.append(sentence)
        delivered_chars += len(sentence)

    if result:
        return "".join(result)
    return _shorten_first_utterance(clean, max_chars)


def _first_sentence_boundary(text: str) -> int | None:
    for index, character in enumerate(text, start=1):
        if character in _HARD_ENDINGS or character in "\r\n":
            return index
    return None


def _shorten_first_utterance(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text.strip()
    prefix = text[:max_chars]
    minimum_boundary = max(8, max_chars // 2)
    for endings in (_HARD_ENDINGS, _SOFT_ENDINGS):
        for index in range(len(prefix) - 1, minimum_boundary - 2, -1):
            if prefix[index] not in endings:
                continue
            candidate = prefix[: index + 1].strip()
            if endings is _SOFT_ENDINGS:
                candidate = candidate.rstrip("\uff0c\uff1b\uff1a\u3001,;: ") + "\u3002"
            return candidate
    if max_chars == 1:
        return "\u2026"
    return prefix[: max_chars - 1].rstrip("\uff0c\uff1b\uff1a\u3001,;: ") + "\u2026"
