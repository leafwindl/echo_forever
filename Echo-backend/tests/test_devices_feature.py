import io
import math
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import av
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.devices.application.process_voice_turn import ProcessDeviceVoiceTurn
from features.devices.domain.entities import DeviceTurnResult
from features.devices.infrastructure.adapters import parse_personal_device_map
from features.devices.infrastructure.audio_codec import (
    OpusPacketDecoder,
    encode_audio_bytes_to_opus_packets,
)
from features.devices.infrastructure.endpoint_detector import (
    AudioEndpointDetector,
    pcm16_rms,
)
from features.devices.interface import router as device_router


def _sine_pcm(sample_rate: int, duration_seconds: float = 0.6) -> bytes:
    samples = int(sample_rate * duration_seconds)
    output = bytearray()
    for index in range(samples):
        value = int(7000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        output.extend(value.to_bytes(2, "little", signed=True))
    return bytes(output)


def _constant_pcm(sample_rate: int, duration_seconds: float, amplitude: int) -> bytes:
    sample = amplitude.to_bytes(2, "little", signed=True)
    return sample * int(sample_rate * duration_seconds)


def _wav_bytes(sample_rate: int = 22050) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(_sine_pcm(sample_rate))
    return output.getvalue()


def _encode_pcm_packets(pcm16: bytes, sample_rate: int) -> tuple[bytes, ...]:
    encoder = av.CodecContext.create("libopus", "w")
    encoder.sample_rate = sample_rate
    encoder.layout = "mono"
    encoder.format = "s16"
    encoder.bit_rate = 24000
    encoder.options = {"frame_duration": "60"}
    encoder.open()

    packets: list[bytes] = []
    frame_samples = sample_rate * 60 // 1000
    frame_bytes = frame_samples * 2
    for offset in range(0, len(pcm16), frame_bytes):
        chunk = pcm16[offset : offset + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk += b"\x00" * (frame_bytes - len(chunk))
        frame = av.AudioFrame(format="s16", layout="mono", samples=frame_samples)
        frame.sample_rate = sample_rate
        frame.planes[0].update(chunk)
        packets.extend(bytes(packet) for packet in encoder.encode(frame))
    packets.extend(bytes(packet) for packet in encoder.encode(None))
    return tuple(packets)


class DeviceAudioCodecTests(unittest.TestCase):
    def test_decodes_device_opus_packets_to_16k_pcm(self):
        packets = _encode_pcm_packets(_sine_pcm(16000), 16000)
        decoder = OpusPacketDecoder(output_sample_rate=16000)

        for packet in packets:
            decoder.push(packet)
        self.assertGreater(decoder.buffered_bytes, 16000)
        result = decoder.finish()

        self.assertGreater(len(result), 16000)
        self.assertEqual(len(result) % 2, 0)
        self.assertEqual(decoder.buffered_bytes, 0)

    def test_encodes_tts_audio_as_24k_opus_packets(self):
        packets = encode_audio_bytes_to_opus_packets(_wav_bytes())

        self.assertGreater(len(packets), 5)
        decoder = OpusPacketDecoder(output_sample_rate=24000)
        for packet in packets:
            decoder.push(packet)
        result = decoder.finish()
        self.assertGreater(len(result), 24000)


class DeviceEndpointDetectorTests(unittest.TestCase):
    def test_detects_silence_only_after_minimum_speech(self):
        detector = AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=1000,
            minimum_speech_ms=180,
            speech_rms_threshold=500,
        )

        self.assertGreater(pcm16_rms(_sine_pcm(16000, 0.06)), 500)
        self.assertFalse(detector.push(b"\x00\x00" * 16000))
        for _ in range(3):
            self.assertFalse(detector.push(_sine_pcm(16000, 0.06)))
        self.assertFalse(detector.push(b"\x00\x00" * 15200))
        self.assertTrue(detector.push(b"\x00\x00" * 800))

    def test_short_noise_does_not_arm_endpoint_detection(self):
        detector = AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=1000,
            minimum_speech_ms=180,
            speech_rms_threshold=500,
        )

        self.assertFalse(detector.push(_sine_pcm(16000, 0.06)))
        self.assertFalse(detector.push(b"\x00\x00" * 16000))
        self.assertFalse(detector.speech_started)

    def test_calibrates_above_steady_background_and_trims_silence(self):
        detector = AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=800,
            minimum_speech_ms=180,
            speech_rms_threshold=500,
        )
        chunks = [
            _constant_pcm(16000, 0.06, 800),
            _constant_pcm(16000, 0.06, 800),
            _constant_pcm(16000, 0.06, 800),
            _constant_pcm(16000, 0.06, 800),
            _constant_pcm(16000, 0.06, 800),
            _sine_pcm(16000, 0.06),
            _sine_pcm(16000, 0.06),
            _sine_pcm(16000, 0.06),
        ]
        chunks.extend(_constant_pcm(16000, 0.06, 800) for _ in range(14))

        detected = False
        for chunk in chunks:
            detected = detector.push(chunk)
            if detected:
                break

        self.assertTrue(detected)
        self.assertGreater(detector.active_rms_threshold, 800)
        raw_audio = b"".join(chunks)
        trimmed_audio = detector.trim(raw_audio)
        self.assertLess(len(trimmed_audio), len(raw_audio))
        self.assertGreaterEqual(len(trimmed_audio), len(_sine_pcm(16000, 0.18)))

    def test_reports_capture_and_speech_elapsed_time(self):
        detector = AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=800,
            minimum_speech_ms=180,
            speech_rms_threshold=500,
            calibration_ms=0,
        )

        self.assertFalse(detector.push(b"\x00\x00" * 1600))
        self.assertEqual(detector.elapsed_ms, 100)
        self.assertEqual(detector.speech_elapsed_ms, 0)
        for _ in range(3):
            self.assertFalse(detector.push(_sine_pcm(16000, 0.06)))

        self.assertTrue(detector.speech_started)
        self.assertTrue(detector.has_speech_candidate)
        self.assertEqual(detector.speech_elapsed_ms, 180)


class FakeRecognizer:
    async def recognize_pcm16(self, audio_bytes: bytes) -> str:
        self.audio_bytes = audio_bytes
        return "我回来了"


class FakeConversation:
    async def reply(self, *, user_id: str, user_text: str, request_id: str):
        self.call = (user_id, user_text, request_id)
        return DeviceTurnResult(
            user_text=user_text,
            reply="欢迎回来。",
            audio_urls=("https://example.test/reply.wav",),
        )


class FakeNotifier:
    async def notify_latest_turn(self, user_id: str) -> None:
        self.user_id = user_id


class DeviceVoiceTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognizes_runs_echo_and_notifies_app(self):
        recognizer = FakeRecognizer()
        conversation = FakeConversation()
        notifier = FakeNotifier()
        on_recognized = AsyncMock()
        use_case = ProcessDeviceVoiceTurn(
            recognizer=recognizer,
            conversation=conversation,
            notifier=notifier,
        )

        result = await use_case.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 800,
            request_id="request-1",
            on_recognized=on_recognized,
        )

        self.assertEqual(result.reply, "欢迎回来。")
        self.assertEqual(conversation.call, ("user-1", "我回来了", "request-1"))
        self.assertEqual(notifier.user_id, "user-1")
        on_recognized.assert_awaited_once_with("我回来了")

    def test_parses_personal_device_mapping(self):
        mapping = parse_personal_device_map(
            '{"AA:BB|CLIENT-1":"user-1"}'
        )

        self.assertEqual(mapping, {"aa:bb|client-1": "user-1"})

    def test_resolves_first_flash_client_id_by_device_wildcard(self):
        with patch.object(
            device_router.settings,
            "echo_device_user_map_json",
            '{"AA:BB|*":"user-1"}',
        ):
            self.assertEqual(
                device_router._resolve_device_user("aa:bb", "new-client-id"),
                "user-1",
            )


class FakeDeviceTurnProcessor:
    def __init__(self):
        self.calls = 0

    async def execute(
        self,
        *,
        user_id: str,
        pcm16_audio: bytes,
        request_id: str,
        on_recognized,
    ) -> DeviceTurnResult:
        if user_id != "user-1" or not pcm16_audio:
            raise AssertionError("Unexpected device turn input")
        if not request_id.startswith("device-"):
            raise AssertionError("Device turn request id is missing its namespace")
        self.calls += 1
        await on_recognized(f"第 {self.calls} 轮")
        return DeviceTurnResult(
            user_text=f"第 {self.calls} 轮",
            reply=f"第 {self.calls} 轮回复",
            audio_urls=("https://example.test/reply.wav",),
        )


class DeviceWebSocketTests(unittest.TestCase):
    def test_auto_mode_resets_silent_capture_without_disconnect(self):
        app = FastAPI()
        app.include_router(device_router.router)
        processor = FakeDeviceTurnProcessor()
        silent_packets = _encode_pcm_packets(b"\x00\x00" * int(16000 * 0.6), 16000)
        speech_packets = _encode_pcm_packets(
            _sine_pcm(16000, 0.3) + b"\x00\x00" * int(16000 * 1.2),
            16000,
        )

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(device_router.settings, "echo_device_auto_silence_ms", 800),
            patch.object(device_router.settings, "echo_device_auto_minimum_speech_ms", 180),
            patch.object(device_router.settings, "echo_device_auto_speech_rms_threshold", 500),
            patch.object(device_router.settings, "echo_device_auto_no_speech_timeout_ms", 300),
            patch.object(device_router.settings, "echo_device_playback_start_delay_ms", 0),
            patch.object(device_router.settings, "echo_device_playback_stop_grace_ms", 0),
            patch.object(
                device_router,
                "get_process_device_voice_turn",
                return_value=processor,
            ),
            patch.object(
                device_router.EchoAudioSource,
                "read",
                new=AsyncMock(return_value=_wav_bytes()),
            ),
            patch.object(
                device_router,
                "encode_audio_bytes_to_opus_packets",
                return_value=(b"reply-opus",),
            ),
            TestClient(app) as client,
            client.websocket_connect(
                "/devices/ws",
                headers={
                    "Device-Id": "aa:bb",
                    "Client-Id": "client-1",
                    "Authorization": "Bearer device-secret",
                },
            ) as websocket,
        ):
            websocket.send_json(
                {
                    "type": "hello",
                    "version": 1,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": 16000,
                        "channels": 1,
                        "frame_duration": 60,
                    },
                }
            )
            websocket.receive_json()
            websocket.send_json({"type": "listen", "state": "start", "mode": "auto"})
            for packet in silent_packets:
                websocket.send_bytes(packet)
            for packet in speech_packets:
                websocket.send_bytes(packet)

            self.assertEqual(websocket.receive_json()["type"], "stt")
            self.assertEqual(websocket.receive_json()["state"], "start")
            self.assertEqual(websocket.receive_json()["state"], "sentence_start")
            self.assertEqual(websocket.receive_bytes(), b"reply-opus")
            self.assertEqual(websocket.receive_json()["state"], "stop")

        self.assertEqual(processor.calls, 1)

    def test_auto_mode_processes_turn_after_trailing_silence(self):
        app = FastAPI()
        app.include_router(device_router.router)
        processor = FakeDeviceTurnProcessor()
        speech = _sine_pcm(16000, 0.3)
        silence = b"\x00\x00" * int(16000 * 1.2)
        packets = _encode_pcm_packets(speech + silence, 16000)

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(device_router.settings, "echo_device_auto_silence_ms", 1000),
            patch.object(device_router.settings, "echo_device_auto_minimum_speech_ms", 180),
            patch.object(device_router.settings, "echo_device_auto_speech_rms_threshold", 500),
            patch.object(
                device_router,
                "get_process_device_voice_turn",
                return_value=processor,
            ),
            patch.object(
                device_router.EchoAudioSource,
                "read",
                new=AsyncMock(return_value=_wav_bytes()),
            ),
            patch.object(
                device_router,
                "encode_audio_bytes_to_opus_packets",
                return_value=(b"reply-opus",),
            ),
            TestClient(app) as client,
            client.websocket_connect(
                "/devices/ws",
                headers={
                    "Device-Id": "aa:bb",
                    "Client-Id": "client-1",
                    "Authorization": "Bearer device-secret",
                },
            ) as websocket,
        ):
            websocket.send_json(
                {
                    "type": "hello",
                    "version": 1,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": 16000,
                        "channels": 1,
                        "frame_duration": 60,
                    },
                }
            )
            hello = websocket.receive_json()
            websocket.send_json({"type": "listen", "state": "start", "mode": "auto"})
            for packet in packets:
                websocket.send_bytes(packet)

            stt = websocket.receive_json()
            tts_start = websocket.receive_json()
            sentence_start = websocket.receive_json()
            audio = websocket.receive_bytes()
            tts_stop = websocket.receive_json()

            self.assertEqual(stt["type"], "stt")
            self.assertTrue(stt["text"])
            self.assertEqual(tts_start["state"], "start")
            self.assertEqual(sentence_start["session_id"], hello["session_id"])
            self.assertEqual(audio, b"reply-opus")
            self.assertEqual(tts_stop["state"], "stop")

        self.assertEqual(processor.calls, 1)

    def test_supports_two_consecutive_half_duplex_turns(self):
        app = FastAPI()
        app.include_router(device_router.router)
        processor = FakeDeviceTurnProcessor()
        packets = _encode_pcm_packets(_sine_pcm(16000, 0.12), 16000)

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(
                device_router,
                "get_process_device_voice_turn",
                return_value=processor,
            ),
            patch.object(
                device_router.EchoAudioSource,
                "read",
                new=AsyncMock(return_value=_wav_bytes()),
            ),
            patch.object(
                device_router,
                "encode_audio_bytes_to_opus_packets",
                return_value=(b"reply-opus",),
            ),
            TestClient(app) as client,
            client.websocket_connect(
                "/devices/ws",
                headers={
                    "Device-Id": "aa:bb",
                    "Client-Id": "client-1",
                    "Authorization": "Bearer device-secret",
                },
            ) as websocket,
        ):
            websocket.send_json(
                {
                    "type": "hello",
                    "version": 1,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": 16000,
                        "channels": 1,
                        "frame_duration": 60,
                    },
                }
            )
            hello = websocket.receive_json()
            self.assertEqual(hello["type"], "hello")
            self.assertEqual(hello["audio_params"]["sample_rate"], 24000)

            for turn in (1, 2):
                websocket.send_json({"type": "listen", "state": "start"})
                for packet in packets:
                    websocket.send_bytes(packet)
                websocket.send_json({"type": "listen", "state": "stop"})

                stt = websocket.receive_json()
                tts_start = websocket.receive_json()
                sentence_start = websocket.receive_json()
                audio = websocket.receive_bytes()
                tts_stop = websocket.receive_json()

                self.assertEqual(stt["text"], f"第 {turn} 轮")
                self.assertEqual(tts_start, {
                    "session_id": hello["session_id"],
                    "type": "tts",
                    "state": "start",
                })
                self.assertEqual(sentence_start["text"], f"第 {turn} 轮回复")
                self.assertEqual(audio, b"reply-opus")
                self.assertEqual(tts_stop["state"], "stop")

        self.assertEqual(processor.calls, 2)


if __name__ == "__main__":
    unittest.main()
