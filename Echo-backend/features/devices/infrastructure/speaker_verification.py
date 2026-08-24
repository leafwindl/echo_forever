from __future__ import annotations

import math
import struct


def extract_speaker_embedding(pcm16_audio: bytes) -> list[float]:
    """Extract a small, deterministic voice-shape vector for the prototype.

    This is deliberately a replaceable boundary, not a security-grade biometric
    model. It lets the personal deployment work without adding a heavyweight ML
    runtime; a production model can later implement the same functions.
    """
    if len(pcm16_audio) < 320:
        return []
    sample_count = len(pcm16_audio) // 2
    samples = struct.unpack(f"<{sample_count}h", pcm16_audio[: sample_count * 2])
    frame_size = 320
    frames: list[tuple[float, float]] = []
    for offset in range(0, len(samples) - frame_size + 1, frame_size):
        frame = samples[offset : offset + frame_size]
        rms = math.sqrt(sum(value * value for value in frame) / len(frame)) / 32768.0
        crossings = sum(1 for left, right in zip(frame, frame[1:]) if (left < 0) != (right < 0))
        frames.append((rms, crossings / len(frame)))
    voiced = [frame for frame in frames if frame[0] > 0.01]
    if not voiced:
        return []
    rms_values = [item[0] for item in voiced]
    zcr_values = [item[1] for item in voiced]
    mean_rms = sum(rms_values) / len(rms_values)
    variance = sum((value - mean_rms) ** 2 for value in rms_values) / len(rms_values)
    percentiles = [
        sorted(rms_values)[min(len(rms_values) - 1, int(len(rms_values) * ratio))]
        for ratio in (0.1, 0.25, 0.5, 0.75, 0.9)
    ]
    vector = [
        mean_rms,
        math.sqrt(variance),
        sum(zcr_values) / len(zcr_values),
        *percentiles,
    ]
    # Add coarse energy distribution across eight amplitude bands.
    bands = [0] * 8
    for value in rms_values:
        bands[min(7, int(value * 8))] += 1
    total = float(len(rms_values))
    vector.extend(count / total for count in bands)
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else []


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def audio_quality(pcm16_audio: bytes) -> float:
    embedding = extract_speaker_embedding(pcm16_audio)
    if not embedding:
        return 0.0
    seconds = len(pcm16_audio) / (16000 * 2)
    return max(0.0, min(1.0, min(seconds / 3.0, 1.0)))
