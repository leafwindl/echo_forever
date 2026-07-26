import re

SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?；;\n])")
SOFT_BOUNDARY_PATTERN = re.compile(r"(?<=[，、,:：])")


def split_text_for_speech(text: str, max_chars: int, total_max_chars: int) -> tuple[str, ...]:
    """Split a reply at natural pauses while enforcing hard synthesis limits."""
    clean_text = " ".join(text.strip().split())[:total_max_chars]
    if not clean_text:
        return ()

    segments: list[str] = []
    for sentence in SENTENCE_BOUNDARY_PATTERN.split(clean_text):
        _append_bounded_segment(segments, sentence.strip(), max_chars)
    return tuple(segment for segment in segments if segment)


def _append_bounded_segment(segments: list[str], text: str, max_chars: int) -> None:
    if not text:
        return
    if len(text) <= max_chars:
        segments.append(text)
        return

    buffer = ""
    for part in SOFT_BOUNDARY_PATTERN.split(text):
        part = part.strip()
        if not part:
            continue
        if buffer and len(buffer) + len(part) > max_chars:
            segments.append(buffer)
            buffer = ""
        while len(part) > max_chars:
            if buffer:
                segments.append(buffer)
                buffer = ""
            segments.append(part[:max_chars])
            part = part[max_chars:]
        buffer += part
    if buffer:
        segments.append(buffer)
