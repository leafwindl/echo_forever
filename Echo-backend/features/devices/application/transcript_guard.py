from __future__ import annotations


def maximum_transcript_chars(
    audio_bytes: int,
    *,
    sample_rate: int = 16000,
    minimum_chars: int = 96,
    maximum_chars_per_second: float = 18.0,
) -> int:
    if audio_bytes <= 0 or sample_rate <= 0:
        return minimum_chars
    duration_seconds = audio_bytes / (sample_rate * 2)
    return max(minimum_chars, int(duration_seconds * maximum_chars_per_second))


def is_plausible_device_transcript(
    text: str,
    audio_bytes: int,
    *,
    sample_rate: int = 16000,
) -> bool:
    compact_length = len("".join(text.split()))
    return compact_length <= maximum_transcript_chars(
        audio_bytes,
        sample_rate=sample_rate,
    )
