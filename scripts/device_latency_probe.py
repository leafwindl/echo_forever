from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from array import array
from pathlib import Path
from typing import Any

import av
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from features.devices.infrastructure.audio_codec import StreamingPcmOpusEncoder  # noqa: E402

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 60
FRAME_BYTES = SAMPLE_RATE * FRAME_DURATION_MS // 1000 * 2


def _decode_audio_file(path: Path) -> bytes:
    output = bytearray()
    with av.open(str(path), mode="r") as container:
        stream = next((item for item in container.streams if item.type == "audio"), None)
        if stream is None:
            raise ValueError(f"Audio file has no audio stream: {path}")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for decoded in container.decode(stream):
            for frame in resampler.resample(decoded):
                output.extend(bytes(frame.planes[0])[: frame.samples * 2])
        for frame in resampler.resample(None):
            output.extend(bytes(frame.planes[0])[: frame.samples * 2])
    if not output:
        raise ValueError(f"Audio file decoded to empty PCM: {path}")
    return bytes(output)


def _resample_pcm16(pcm16_audio: bytes, *, source_rate: int) -> bytes:
    frame = av.AudioFrame(format="s16", layout="mono", samples=len(pcm16_audio) // 2)
    frame.sample_rate = source_rate
    frame.planes[0].update(pcm16_audio)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    output = bytearray()
    for converted in resampler.resample(frame):
        output.extend(bytes(converted.planes[0])[: converted.samples * 2])
    for converted in resampler.resample(None):
        output.extend(bytes(converted.planes[0])[: converted.samples * 2])
    return bytes(output)


async def _synthesize_probe_text(text: str) -> bytes:
    from providers.tts_provider import get_tts_provider
    from shared.config import settings

    pcm24 = bytearray()
    async for chunk in get_tts_provider().stream_pcm16(
        text,
        settings.tts_voice_id,
        instruction=settings.cosyvoice_instruction,
    ):
        pcm24.extend(chunk)
    return _resample_pcm16(bytes(pcm24), source_rate=24000)


def _trim_silence(pcm16_audio: bytes, *, threshold: int = 300) -> bytes:
    samples = array("h")
    samples.frombytes(pcm16_audio[: len(pcm16_audio) - len(pcm16_audio) % 2])
    window_samples = SAMPLE_RATE // 50
    active_windows: list[int] = []
    for offset in range(0, len(samples), window_samples):
        window = samples[offset : offset + window_samples]
        if not window:
            continue
        rms = math.sqrt(sum(sample * sample for sample in window) / len(window))
        if rms >= threshold:
            active_windows.append(offset)
    if not active_windows:
        raise ValueError("Probe audio contains no speech above the RMS threshold")
    start = max(0, active_windows[0] - window_samples * 5)
    end = min(len(samples), active_windows[-1] + window_samples * 6)
    return samples[start:end].tobytes()


def _resize_speech(pcm16_audio: bytes, target_seconds: float | None) -> bytes:
    if not target_seconds:
        return pcm16_audio
    target_bytes = int(target_seconds * SAMPLE_RATE * 2)
    repeats = math.ceil(target_bytes / len(pcm16_audio))
    return (pcm16_audio * repeats)[:target_bytes]


def _pad_frame(pcm16_audio: bytes) -> bytes:
    padding = (-len(pcm16_audio)) % FRAME_BYTES
    return pcm16_audio + b"\x00" * padding


def _resolve_device_identity(args: argparse.Namespace) -> tuple[str, str, str]:
    device_id = (args.device_id or os.getenv("ECHO_DEVICE_ID", "")).strip()
    client_id = (args.client_id or os.getenv("ECHO_DEVICE_CLIENT_ID", "")).strip()
    token = (args.token or os.getenv("ECHO_DEVICE_TOKEN", "")).strip()
    if not device_id or not client_id:
        raw_mapping = os.getenv("ECHO_DEVICE_USER_MAP_JSON", "{}")
        mapping = json.loads(raw_mapping)
        if mapping:
            device_key = str(next(iter(mapping))).split("|", maxsplit=1)
            device_id = device_id or device_key[0]
            client_id = client_id or (device_key[1] if len(device_key) > 1 else "")
    if not device_id or not client_id or not token:
        raise ValueError(
            "Device credentials are required through arguments or "
            "ECHO_DEVICE_* environment variables"
        )
    return device_id, client_id, token


def _relative_ms(timestamp: float | None, speech_ended_at: float) -> float | None:
    if timestamp is None:
        return None
    return round((timestamp - speech_ended_at) * 1000, 1)


async def _run_probe(args: argparse.Namespace) -> dict[str, Any]:
    if args.audio_file:
        speech_pcm = _decode_audio_file(Path(args.audio_file))
    elif args.text:
        speech_pcm = await _synthesize_probe_text(args.text)
    else:
        raise ValueError("Provide --audio-file or --text")
    speech_pcm = _resize_speech(_trim_silence(speech_pcm), args.speech_seconds)
    speech_pcm = _pad_frame(speech_pcm)

    encoder = StreamingPcmOpusEncoder(
        sample_rate=SAMPLE_RATE,
        frame_duration_ms=FRAME_DURATION_MS,
    )
    speech_packets = encoder.push(speech_pcm)
    trailing_silence = b"\x00" * int(args.trailing_silence_ms * SAMPLE_RATE * 2 / 1000)
    silence_packets = encoder.push(_pad_frame(trailing_silence)) + encoder.finish()

    device_id, client_id, token = _resolve_device_identity(args)
    timestamps: dict[str, float] = {}
    payloads: dict[str, Any] = {}
    output_packets = 0

    headers = {
        "Device-Id": device_id,
        "Client-Id": client_id,
        "Authorization": f"Bearer {token}",
    }
    async with websockets.connect(
        args.url,
        additional_headers=headers,
        open_timeout=args.timeout,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "hello",
                    "version": 1,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": SAMPLE_RATE,
                        "channels": 1,
                        "frame_duration": FRAME_DURATION_MS,
                    },
                }
            )
        )
        hello = json.loads(await asyncio.wait_for(websocket.recv(), timeout=args.timeout))
        if hello.get("type") != "hello":
            raise RuntimeError(f"Unexpected device hello response: {hello}")

        async def receive_replies() -> None:
            nonlocal output_packets
            async for message in websocket:
                received_at = time.perf_counter()
                if isinstance(message, bytes):
                    output_packets += 1
                    timestamps.setdefault("first_audio", received_at)
                    continue
                payload = json.loads(message)
                message_type = payload.get("type")
                if message_type == "stt":
                    timestamps.setdefault("stt", received_at)
                    payloads["stt"] = payload.get("text", "")
                elif message_type == "tts":
                    state = payload.get("state")
                    if state == "start":
                        timestamps.setdefault("tts_start", received_at)
                    elif state == "sentence_start":
                        timestamps.setdefault("sentence_start", received_at)
                        payloads.setdefault("first_sentence", payload.get("text", ""))
                    elif state == "stop":
                        timestamps["tts_stop"] = received_at
                        return
                elif message_type in {"alert", "error"}:
                    raise RuntimeError(f"Device server returned {message_type}: {payload}")

        receiver = asyncio.create_task(receive_replies())
        await websocket.send(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
        packet_interval = FRAME_DURATION_MS / 1000
        send_started_at = time.perf_counter()
        packet_index = 0
        for packet in speech_packets:
            send_at = send_started_at + packet_index * packet_interval
            await asyncio.sleep(max(0, send_at - time.perf_counter()))
            await websocket.send(packet)
            packet_index += 1
        speech_ended_at = time.perf_counter()
        for packet in silence_packets:
            send_at = send_started_at + packet_index * packet_interval
            await asyncio.sleep(max(0, send_at - time.perf_counter()))
            await websocket.send(packet)
            packet_index += 1

        try:
            await asyncio.wait_for(receiver, timeout=args.timeout)
        finally:
            if not receiver.done():
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)

    return {
        "speech_s": round(len(speech_pcm) / (SAMPLE_RATE * 2), 2),
        "speech_packets": len(speech_packets),
        "trailing_silence_ms": args.trailing_silence_ms,
        "recognized_text": payloads.get("stt", ""),
        "first_sentence": payloads.get("first_sentence", ""),
        "speech_end_to_stt_ms": _relative_ms(timestamps.get("stt"), speech_ended_at),
        "speech_end_to_tts_start_ms": _relative_ms(timestamps.get("tts_start"), speech_ended_at),
        "speech_end_to_sentence_start_ms": _relative_ms(
            timestamps.get("sentence_start"), speech_ended_at
        ),
        "speech_end_to_first_audio_ms": _relative_ms(
            timestamps.get("first_audio"), speech_ended_at
        ),
        "speech_end_to_stop_ms": _relative_ms(timestamps.get("tts_stop"), speech_ended_at),
        "output_packets": output_packets,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure an Echo device voice turn while sending and receiving concurrently."
    )
    parser.add_argument(
        "--url",
        default=os.getenv("ECHO_DEVICE_WS_URL", "ws://127.0.0.1:8000/devices/ws"),
    )
    parser.add_argument("--device-id")
    parser.add_argument("--client-id")
    parser.add_argument("--token")
    parser.add_argument("--audio-file")
    parser.add_argument("--text")
    parser.add_argument("--speech-seconds", type=float)
    parser.add_argument("--trailing-silence-ms", type=int, default=720)
    parser.add_argument("--timeout", type=float, default=60)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    print(json.dumps(asyncio.run(_run_probe(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
