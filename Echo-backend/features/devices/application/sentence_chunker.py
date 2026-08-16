from __future__ import annotations

_HARD_ENDINGS = frozenset("。！？!?；;")
_SOFT_ENDINGS = frozenset("，,、：:")


class SentenceChunker:
    """Turn streamed LLM text into TTS-sized natural Chinese phrases."""

    def __init__(self, *, max_chars: int = 32, min_chars: int | None = None):
        if max_chars < 8:
            raise ValueError("Sentence chunk size is too small")
        resolved_min_chars = min(12, max_chars) if min_chars is None else min_chars
        if resolved_min_chars < 1 or resolved_min_chars > max_chars:
            raise ValueError("Sentence chunk minimum must be within the maximum")
        self.max_chars = max_chars
        self.min_chars = resolved_min_chars
        self._buffer = ""

    def push(self, text: str) -> tuple[str, ...]:
        self._buffer += text
        chunks: list[str] = []
        while self._buffer:
            boundary = self._find_boundary()
            if boundary is None:
                break
            chunks.append(self._take(boundary))
        return tuple(chunks)

    def finish(self) -> tuple[str, ...]:
        remaining = self._buffer.strip()
        self._buffer = ""
        return (remaining,) if remaining else ()

    def _find_boundary(self) -> int | None:
        search_limit = min(len(self._buffer), self.max_chars)
        soft_boundaries: list[int] = []
        for index, character in enumerate(self._buffer[:search_limit], start=1):
            if character in _HARD_ENDINGS and index >= self.min_chars:
                return index
            if character in _SOFT_ENDINGS and index >= self.min_chars:
                soft_boundaries.append(index)
        if soft_boundaries:
            return soft_boundaries[-1]
        if len(self._buffer) >= self.max_chars:
            return self.max_chars
        return None

    def _take(self, length: int) -> str:
        chunk = self._buffer[:length].strip()
        self._buffer = self._buffer[length:]
        if not chunk and self._buffer:
            return self._take(min(self.max_chars, len(self._buffer)))
        return chunk
