from __future__ import annotations

_HARD_ENDINGS = frozenset("。！？!?；;")
_SOFT_ENDINGS = frozenset("，,、：:")


class SentenceChunker:
    """Turn streamed LLM text into TTS-sized natural Chinese phrases."""

    def __init__(self, *, max_chars: int = 24):
        if max_chars < 8:
            raise ValueError("Sentence chunk size is too small")
        self.max_chars = max_chars
        self.min_soft_chars = min(8, max_chars)
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
        for index, character in enumerate(self._buffer, start=1):
            if character in _HARD_ENDINGS:
                return index
            if character in _SOFT_ENDINGS and index >= self.min_soft_chars:
                return index
        if len(self._buffer) >= self.max_chars:
            soft_boundaries = [
                index
                for index, character in enumerate(
                    self._buffer[: self.max_chars],
                    start=1,
                )
                if character in _SOFT_ENDINGS and index >= self.min_soft_chars
            ]
            return soft_boundaries[-1] if soft_boundaries else self.max_chars
        return None

    def _take(self, length: int) -> str:
        chunk = self._buffer[:length].strip()
        self._buffer = self._buffer[length:]
        if not chunk and self._buffer:
            return self._take(min(self.max_chars, len(self._buffer)))
        return chunk
