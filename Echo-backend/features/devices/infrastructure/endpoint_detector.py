from __future__ import annotations

import math
import statistics
import struct


def pcm16_rms(pcm16_audio: bytes) -> float:
    """Return the RMS level of little-endian mono PCM16 audio."""
    sample_bytes = len(pcm16_audio) - (len(pcm16_audio) % 2)
    if sample_bytes == 0:
        return 0.0
    samples = struct.iter_unpack("<h", memoryview(pcm16_audio)[:sample_bytes])
    square_sum = sum(sample[0] * sample[0] for sample in samples)
    return math.sqrt(square_sum / (sample_bytes // 2))


class AudioEndpointDetector:
    """Detect the end of an utterance from decoded PCM chunks."""

    def __init__(
        self,
        *,
        sample_rate: int,
        silence_ms: int,
        minimum_speech_ms: int,
        speech_rms_threshold: int,
        calibration_ms: int = 300,
        noise_multiplier: float = 2.5,
        pre_roll_ms: int = 240,
        trailing_audio_ms: int = 300,
    ):
        self.sample_rate = sample_rate
        self.silence_ms = silence_ms
        self.minimum_speech_ms = minimum_speech_ms
        self.speech_rms_threshold = speech_rms_threshold
        self.calibration_ms = calibration_ms
        self.noise_multiplier = noise_multiplier
        self.pre_roll_ms = pre_roll_ms
        self.trailing_audio_ms = trailing_audio_ms
        self.voiced_ms = 0.0
        self.trailing_silence_ms = 0.0
        self.speech_started = False
        self.noise_floor_rms = 0.0
        self.active_rms_threshold = float(speech_rms_threshold)
        self.speech_start_sample: int | None = None
        self.last_voiced_end_sample: int | None = None
        self._candidate_start_sample: int | None = None
        self._total_samples = 0
        self._calibration_samples = 0
        self._calibration_chunks: list[tuple[int, int, float]] = []
        self._calibrated = calibration_ms == 0

    def push(self, pcm16_audio: bytes) -> bool:
        sample_count = len(pcm16_audio) // 2
        if sample_count == 0:
            return False
        chunk_start_sample = self._total_samples
        self._total_samples += sample_count
        rms = pcm16_rms(pcm16_audio)

        if not self._calibrated:
            self._calibration_chunks.append((chunk_start_sample, sample_count, rms))
            self._calibration_samples += sample_count
            calibration_target = self.sample_rate * self.calibration_ms // 1000
            if self._calibration_samples < calibration_target:
                return False
            levels = sorted(level for _, _, level in self._calibration_chunks)
            quiet_levels = levels[: max(1, (len(levels) + 1) // 2)]
            self.noise_floor_rms = statistics.fmean(quiet_levels)
            self.active_rms_threshold = max(
                float(self.speech_rms_threshold),
                min(
                    self.noise_floor_rms * self.noise_multiplier,
                    self.speech_rms_threshold * 4.0,
                ),
            )
            self._calibrated = True
            for start_sample, samples, level in self._calibration_chunks:
                self._classify_level(start_sample, samples, level)
            self._calibration_chunks.clear()
            return False

        return self._classify_level(chunk_start_sample, sample_count, rms)

    @property
    def elapsed_ms(self) -> float:
        return self._total_samples * 1000 / self.sample_rate

    @property
    def speech_elapsed_ms(self) -> float:
        if self.speech_start_sample is None:
            return 0.0
        return (self._total_samples - self.speech_start_sample) * 1000 / self.sample_rate

    @property
    def has_speech_candidate(self) -> bool:
        return self._candidate_start_sample is not None

    def _classify_level(self, chunk_start_sample: int, sample_count: int, rms: float) -> bool:
        chunk_ms = sample_count * 1000 / self.sample_rate
        if rms >= self.active_rms_threshold:
            if self._candidate_start_sample is None:
                self._candidate_start_sample = chunk_start_sample
            self.voiced_ms += chunk_ms
            self.trailing_silence_ms = 0.0
            self.last_voiced_end_sample = chunk_start_sample + sample_count
            if self.voiced_ms >= self.minimum_speech_ms:
                self.speech_started = True
                if self.speech_start_sample is None:
                    self.speech_start_sample = self._candidate_start_sample
            return False

        if not self.speech_started:
            self.voiced_ms = 0.0
            self._candidate_start_sample = None
            return False

        self.trailing_silence_ms += chunk_ms
        return self.trailing_silence_ms >= self.silence_ms

    def trim(self, pcm16_audio: bytes) -> bytes:
        if self.speech_start_sample is None or self.last_voiced_end_sample is None:
            return pcm16_audio
        pre_roll_samples = self.sample_rate * self.pre_roll_ms // 1000
        trailing_samples = self.sample_rate * self.trailing_audio_ms // 1000
        start_sample = max(0, self.speech_start_sample - pre_roll_samples)
        end_sample = min(
            len(pcm16_audio) // 2,
            self.last_voiced_end_sample + trailing_samples,
        )
        if end_sample <= start_sample:
            return pcm16_audio
        return pcm16_audio[start_sample * 2 : end_sample * 2]
