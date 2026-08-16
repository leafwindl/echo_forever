from __future__ import annotations

import io
import logging
from fractions import Fraction

import av

logger = logging.getLogger(__name__)


class Pcm16SilenceLimiter:
    """Cap long digital-silence runs without changing normal speech timing."""

    def __init__(
        self,
        *,
        sample_rate: int,
        maximum_silence_ms: int,
        rms_threshold: int,
        window_duration_ms: int = 20,
    ):
        if sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
        if maximum_silence_ms < window_duration_ms:
            raise ValueError("Maximum silence must cover at least one analysis window")
        if rms_threshold < 0:
            raise ValueError("Silence RMS threshold cannot be negative")
        self.sample_rate = sample_rate
        self.maximum_silence_ms = maximum_silence_ms
        self.rms_threshold = rms_threshold
        self.window_duration_ms = window_duration_ms
        self.window_samples = sample_rate * window_duration_ms // 1000
        self.window_bytes = self.window_samples * 2
        self.maximum_silence_bytes = (
            maximum_silence_ms // window_duration_ms * self.window_bytes
        )
        self._pcm = bytearray()
        self._pending_silence = bytearray()
        self.input_bytes = 0
        self.output_bytes = 0
        self.trimmed_bytes = 0

    @property
    def trimmed_silence_ms(self) -> float:
        return self.trimmed_bytes * 1000 / (self.sample_rate * 2)

    def push(self, pcm16_audio: bytes) -> bytes:
        if pcm16_audio:
            self._pcm.extend(pcm16_audio)
            self.input_bytes += len(pcm16_audio)

        output = bytearray()
        while len(self._pcm) >= self.window_bytes:
            frame = bytes(self._pcm[: self.window_bytes])
            del self._pcm[: self.window_bytes]
            if self._is_silent(frame):
                self._pending_silence.extend(frame)
                continue
            self._flush_pending_silence(output)
            output.extend(frame)
        self.output_bytes += len(output)
        return bytes(output)

    def finish(self) -> bytes:
        output = bytearray()
        if len(self._pcm) % 2:
            self._pcm.pop()
        if self._pcm:
            tail = bytes(self._pcm)
            self._pcm.clear()
            if self._is_silent(tail):
                self._pending_silence.extend(tail)
            else:
                self._flush_pending_silence(output)
                output.extend(tail)
        self._flush_pending_silence(output)
        self.output_bytes += len(output)
        return bytes(output)

    def _flush_pending_silence(self, output: bytearray) -> None:
        if not self._pending_silence:
            return
        kept_bytes = min(len(self._pending_silence), self.maximum_silence_bytes)
        output.extend(self._pending_silence[:kept_bytes])
        self.trimmed_bytes += len(self._pending_silence) - kept_bytes
        self._pending_silence.clear()

    def _is_silent(self, pcm16_audio: bytes) -> bool:
        samples = memoryview(pcm16_audio).cast("h")
        if not samples:
            return True
        mean_square = sum(sample * sample for sample in samples) / len(samples)
        return mean_square <= self.rms_threshold * self.rms_threshold


class OpusPacketDecoder:
    """Decode raw Opus packets from Xiaozhi protocol v1 into PCM16LE."""

    def __init__(self, *, output_sample_rate: int = 16000):
        self.output_sample_rate = output_sample_rate
        self._decoder = av.CodecContext.create("opus", "r")
        self._decoder.open()
        self._resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=output_sample_rate,
        )
        self._pcm = bytearray()

    def push(self, payload: bytes) -> bytes:
        if not payload:
            return b""
        start = len(self._pcm)
        for frame in self._decoder.decode(av.Packet(payload)):
            self._append_resampled(frame)
        return bytes(self._pcm[start:])

    @property
    def buffered_bytes(self) -> int:
        return len(self._pcm)

    def finish(self) -> bytes:
        for frame in self._decoder.decode(None):
            self._append_resampled(frame)
        for frame in self._resampler.resample(None):
            self._append_pcm_frame(frame)
        audio = bytes(self._pcm)
        self._pcm.clear()
        return audio

    def _append_resampled(self, frame: av.AudioFrame) -> None:
        for converted in self._resampler.resample(frame):
            self._append_pcm_frame(converted)

    def _append_pcm_frame(self, frame: av.AudioFrame) -> None:
        bytes_per_sample = 2
        self._pcm.extend(bytes(frame.planes[0])[: frame.samples * bytes_per_sample])


class StreamingPcmOpusEncoder:
    """Encode arbitrary PCM16 chunks into fixed 60 ms device Opus packets."""

    def __init__(
        self,
        *,
        sample_rate: int = 24000,
        frame_duration_ms: int = 60,
        bit_rate: int = 24000,
        maximum_silence_ms: int | None = None,
        silence_rms_threshold: int = 300,
    ):
        if frame_duration_ms not in {20, 40, 60}:
            raise ValueError("Unsupported Opus frame duration")
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = sample_rate * frame_duration_ms // 1000
        self.frame_bytes = self.frame_samples * 2
        self._pcm = bytearray()
        self._encoder = av.CodecContext.create("libopus", "w")
        self._encoder.sample_rate = sample_rate
        self._encoder.layout = "mono"
        self._encoder.format = "s16"
        self._encoder.bit_rate = bit_rate
        self._encoder.time_base = Fraction(1, sample_rate)
        self._encoder.options = {"frame_duration": str(frame_duration_ms)}
        self._encoder.open()
        self._next_pts = 0
        self._silence_limiter = (
            Pcm16SilenceLimiter(
                sample_rate=sample_rate,
                maximum_silence_ms=maximum_silence_ms,
                rms_threshold=silence_rms_threshold,
            )
            if maximum_silence_ms is not None
            else None
        )

    @property
    def trimmed_silence_ms(self) -> float:
        if self._silence_limiter is None:
            return 0.0
        return self._silence_limiter.trimmed_silence_ms

    def push(self, pcm16_audio: bytes) -> tuple[bytes, ...]:
        if self._silence_limiter is not None:
            pcm16_audio = self._silence_limiter.push(pcm16_audio)
        if pcm16_audio:
            self._pcm.extend(pcm16_audio[: len(pcm16_audio) - (len(pcm16_audio) % 2)])
        packets: list[bytes] = []
        while len(self._pcm) >= self.frame_bytes:
            packets.extend(self._encode_frame(bytes(self._pcm[: self.frame_bytes])))
            del self._pcm[: self.frame_bytes]
        return tuple(packets)

    def finish(self) -> tuple[bytes, ...]:
        packets: list[bytes] = []
        if self._silence_limiter is not None:
            self._pcm.extend(self._silence_limiter.finish())
        while len(self._pcm) >= self.frame_bytes:
            packets.extend(self._encode_frame(bytes(self._pcm[: self.frame_bytes])))
            del self._pcm[: self.frame_bytes]
        if self._pcm:
            padded = bytes(self._pcm) + b"\x00" * (self.frame_bytes - len(self._pcm))
            packets.extend(self._encode_frame(padded))
            self._pcm.clear()
        packets.extend(bytes(packet) for packet in self._encoder.encode(None))
        return tuple(packets)

    def _encode_frame(self, pcm16_audio: bytes) -> tuple[bytes, ...]:
        frame = av.AudioFrame(
            format="s16",
            layout="mono",
            samples=self.frame_samples,
        )
        frame.sample_rate = self.sample_rate
        frame.pts = self._next_pts
        frame.time_base = Fraction(1, self.sample_rate)
        frame.planes[0].update(pcm16_audio)
        self._next_pts += self.frame_samples
        return tuple(bytes(packet) for packet in self._encoder.encode(frame))


def encode_audio_bytes_to_opus_packets(
    audio_bytes: bytes,
    *,
    output_sample_rate: int = 24000,
    frame_duration_ms: int = 60,
    bit_rate: int = 24000,
    maximum_silence_ms: int | None = None,
    silence_rms_threshold: int = 300,
) -> tuple[bytes, ...]:
    if not audio_bytes:
        raise ValueError("TTS audio is empty")
    if frame_duration_ms not in {20, 40, 60}:
        raise ValueError("Unsupported Opus frame duration")

    with av.open(io.BytesIO(audio_bytes), mode="r") as container:
        audio_stream = next(
            (stream for stream in container.streams if stream.type == "audio"),
            None,
        )
        if audio_stream is None:
            raise ValueError("TTS payload contains no audio stream")

        resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=output_sample_rate,
            frame_size=output_sample_rate * frame_duration_ms // 1000,
        )
        encoder = StreamingPcmOpusEncoder(
            sample_rate=output_sample_rate,
            frame_duration_ms=frame_duration_ms,
            bit_rate=bit_rate,
            maximum_silence_ms=maximum_silence_ms,
            silence_rms_threshold=silence_rms_threshold,
        )

        packets: list[bytes] = []
        for decoded in container.decode(audio_stream):
            for frame in resampler.resample(decoded):
                pcm = bytes(frame.planes[0])[: frame.samples * 2]
                packets.extend(encoder.push(pcm))
        for frame in resampler.resample(None):
            pcm = bytes(frame.planes[0])[: frame.samples * 2]
            packets.extend(encoder.push(pcm))
        packets.extend(encoder.finish())

        if encoder.trimmed_silence_ms:
            logger.info(
                "Echo device TTS silence compacted trimmed_ms=%.1f output_packets=%s",
                encoder.trimmed_silence_ms,
                len(packets),
            )

    if not packets:
        raise ValueError("TTS payload could not be encoded as Opus")
    return tuple(packets)
