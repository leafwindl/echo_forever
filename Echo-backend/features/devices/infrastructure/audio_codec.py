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
