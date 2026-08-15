from __future__ import annotations

import io
from fractions import Fraction

import av


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

    def __init__(self, *, sample_rate: int = 24000, frame_duration_ms: int = 60):
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
        self._encoder.bit_rate = 24000
        self._encoder.time_base = Fraction(1, sample_rate)
        self._encoder.options = {"frame_duration": str(frame_duration_ms)}
        self._encoder.open()
        self._next_pts = 0

    def push(self, pcm16_audio: bytes) -> tuple[bytes, ...]:
        if pcm16_audio:
            self._pcm.extend(pcm16_audio[: len(pcm16_audio) - (len(pcm16_audio) % 2)])
        packets: list[bytes] = []
        while len(self._pcm) >= self.frame_bytes:
            packets.extend(self._encode_frame(bytes(self._pcm[: self.frame_bytes])))
            del self._pcm[: self.frame_bytes]
        return tuple(packets)

    def finish(self) -> tuple[bytes, ...]:
        packets: list[bytes] = []
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
        encoder = av.CodecContext.create("libopus", "w")
        encoder.sample_rate = output_sample_rate
        encoder.layout = "mono"
        encoder.format = "s16"
        encoder.bit_rate = bit_rate
        encoder.time_base = Fraction(1, output_sample_rate)
        encoder.options = {"frame_duration": str(frame_duration_ms)}
        encoder.open()

        packets: list[bytes] = []
        next_pts = 0
        for decoded in container.decode(audio_stream):
            for frame in resampler.resample(decoded):
                frame.pts = next_pts
                frame.time_base = Fraction(1, output_sample_rate)
                next_pts += frame.samples
                packets.extend(bytes(packet) for packet in encoder.encode(frame))
        for frame in resampler.resample(None):
            frame.pts = next_pts
            frame.time_base = Fraction(1, output_sample_rate)
            next_pts += frame.samples
            packets.extend(bytes(packet) for packet in encoder.encode(frame))
        packets.extend(bytes(packet) for packet in encoder.encode(None))

    if not packets:
        raise ValueError("TTS payload could not be encoded as Opus")
    return tuple(packets)
