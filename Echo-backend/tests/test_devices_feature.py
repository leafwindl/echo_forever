import asyncio
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

from features.agent.domain.delivery import AgentDeliveryPlanError
from features.chat.domain.entities import ChatReplyDeliveryResult
from features.devices.application.process_voice_turn import ProcessDeviceVoiceTurn
from features.devices.application.sentence_chunker import SentenceChunker
from features.devices.application.stream_voice_turn import StreamDeviceVoiceTurn
from features.devices.application.transcript_guard import (
    is_plausible_device_transcript,
    maximum_transcript_chars,
)
from features.devices.domain.entities import DeviceTurnResult
from features.devices.infrastructure.adapters import (
    EchoConversationService,
    parse_personal_device_map,
)
from features.devices.infrastructure.audio_codec import (
    OpusPacketDecoder,
    Pcm16SilenceLimiter,
    StreamingPcmOpusEncoder,
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

    def test_limits_long_tts_silence_without_trimming_speech(self):
        limiter = Pcm16SilenceLimiter(
            sample_rate=24000,
            maximum_silence_ms=240,
            rms_threshold=300,
        )
        speech = _constant_pcm(24000, 0.3, 4000)
        long_silence = _constant_pcm(24000, 0.8, 0)
        source = speech + long_silence + speech

        output = bytearray()
        for offset in range(0, len(source), 1379):
            output.extend(limiter.push(source[offset : offset + 1379]))
        output.extend(limiter.finish())

        expected_bytes = len(speech) * 2 + 24000 * 2 * 240 // 1000
        self.assertEqual(len(output), expected_bytes)
        self.assertAlmostEqual(limiter.trimmed_silence_ms, 560.0, places=1)

    def test_non_streaming_encoder_compacts_long_tts_silence(self):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(
                _constant_pcm(24000, 0.3, 4000)
                + _constant_pcm(24000, 0.8, 0)
                + _constant_pcm(24000, 0.3, 4000)
            )

        original = encode_audio_bytes_to_opus_packets(output.getvalue())
        compacted = encode_audio_bytes_to_opus_packets(
            output.getvalue(),
            maximum_silence_ms=240,
            silence_rms_threshold=300,
        )

        self.assertGreater(len(original) - len(compacted), 7)


class SentenceChunkerTests(unittest.TestCase):
    def test_prefers_natural_punctuation_and_flushes_remainder(self):
        chunker = SentenceChunker(max_chars=8)

        self.assertEqual(chunker.push("你好，今天很好。"), ("你好，今天很好。",))
        self.assertEqual(chunker.push("我们继续"), ())
        self.assertEqual(chunker.finish(), ("我们继续",))

    def test_bounds_unpunctuated_stream(self):
        chunker = SentenceChunker(max_chars=8)

        self.assertEqual(chunker.push("一二三四五六七八九"), ("一二三四五六七八",))
        self.assertEqual(chunker.finish(), ("九",))

    def test_emits_a_natural_clause_at_a_later_comma(self):
        chunker = SentenceChunker(max_chars=18)

        self.assertEqual(
            chunker.push("叶子，今天白天刚忙完汇报，"),
            ("叶子，今天白天刚忙完汇报，",),
        )
        self.assertEqual(chunker.finish(), ())

    def test_does_not_emit_an_overly_short_comma_fragment(self):
        chunker = SentenceChunker(max_chars=18)

        self.assertEqual(chunker.push("叶子，"), ())
        self.assertEqual(chunker.push("我在听。"), ())
        self.assertEqual(chunker.push("你慢慢说。"), ("叶子，我在听。你慢慢说。",))

    def test_coalesces_short_sentences_to_reduce_tts_requests(self):
        chunker = SentenceChunker(max_chars=32, min_chars=12)

        self.assertEqual(chunker.push("好呀。"), ())
        self.assertEqual(chunker.push("我陪你聊。"), ())
        self.assertEqual(
            chunker.push("你刚才最在意的是哪一段？"),
            ("好呀。我陪你聊。你刚才最在意的是哪一段？",),
        )


class DeviceTranscriptGuardTests(unittest.TestCase):
    def test_rejects_transcript_impossible_for_audio_duration(self):
        audio_bytes = 4 * 16000 * 2

        self.assertEqual(maximum_transcript_chars(audio_bytes), 96)
        self.assertFalse(is_plausible_device_transcript("很长" * 200, audio_bytes))

    def test_accepts_normal_transcript(self):
        self.assertTrue(
            is_plausible_device_transcript("我刚刚在看视频。", 2 * 16000 * 2)
        )


class DeviceStreamingCodecTests(unittest.TestCase):
    def test_streaming_encoder_emits_packets_after_incremental_pcm(self):
        encoder = StreamingPcmOpusEncoder()

        packets_before_frame = encoder.push(b"\x00\x00" * 1000)
        packets_after_frame = encoder.push(b"\x00\x00" * 1000)
        packets_after_finish = encoder.finish()

        self.assertEqual(packets_before_frame, ())
        self.assertTrue(packets_after_frame or packets_after_finish)


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
    async def test_recognizes_runs_echo_and_notifies_turn_completion(self):
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

    async def test_device_conversation_persists_hidden_device_channel(self):
        delivery = ChatReplyDeliveryResult(reply="我在。")
        with patch(
            "features.devices.infrastructure.adapters.send_chat_message",
            new=AsyncMock(return_value=delivery),
        ) as send_message:
            result = await EchoConversationService().reply(
                user_id="user-1",
                user_text="你好",
                request_id="device-request",
                synthesize_voice=False,
            )

        self.assertEqual(result.reply, "我在。")
        send_message.assert_awaited_once_with(
            user_id="user-1",
            message="你好",
            conversation_mode="call",
            request_id="device-request",
            on_text_delta=None,
            on_progress_text=None,
            synthesize_voice=False,
            message_channel="device_voice",
            message_visibility="device_history",
        )

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


class FakeStreamingConversation:
    async def reply(
        self,
        *,
        user_id,
        user_text,
        request_id,
        on_reply_delta=None,
        on_progress_text=None,
        synthesize_voice=True,
    ):
        del on_progress_text
        self.arguments = (user_id, user_text, request_id, synthesize_voice)
        await on_reply_delta("第一句。第二句")
        return DeviceTurnResult(user_text=user_text, reply="第一句。第二句", audio_urls=())


class FakeStreamingSpeech:
    def __init__(self):
        self.phrases = []

    async def _stream(self, text):
        self.phrases.append(text)
        yield b"\x00\x00" * 1440

    def stream_pcm16(self, text):
        return self._stream(text)


class FakeStreamingNotifier:
    async def notify_latest_turn(self, user_id):
        self.user_id = user_id


class FakeDeviceRealtimeAsrSession:
    def __init__(self):
        self.audio = bytearray()
        self.finished = False
        self.closed = False
        self.failed = False
        self._updates = asyncio.Queue()

    async def send_audio(self, audio_bytes):
        self.audio.extend(audio_bytes)

    async def finish(self):
        self.finished = True
        await self._updates.put(type("Update", (), {"text": "实时识别结果", "is_final": True})())

    async def receive_update(self):
        return await self._updates.get()

    async def close(self):
        self.closed = True


class FakeEmptyDeviceRealtimeAsrSession(FakeDeviceRealtimeAsrSession):
    async def finish(self):
        self.finished = True
        await self._updates.put(type("Update", (), {"text": "", "is_final": True})())


class FakeImplausibleDeviceRealtimeAsrSession(FakeDeviceRealtimeAsrSession):
    async def finish(self):
        self.finished = True
        await self._updates.put(
            type(
                "Update",
                (),
                {"text": "异常长文本" * 80, "is_final": True},
            )()
        )


class FakeStreamingDeviceTurn:
    def __init__(self):
        self.recognized_text = None

    async def execute(
        self,
        *,
        user_id,
        pcm16_audio,
        request_id,
        on_recognized,
        on_tts_start,
        on_sentence_start,
        on_audio_packet,
        on_tts_stop,
        recognized_text=None,
        latency=None,
    ):
        del user_id, pcm16_audio, request_id, latency
        self.recognized_text = recognized_text
        await on_recognized(recognized_text or "batch-result")
        await on_tts_start()
        await on_sentence_start("回复")
        await on_audio_packet(b"stream-opus")
        await on_tts_stop()
        return DeviceTurnResult(
            user_text=recognized_text or "batch-result",
            reply="回复",
            audio_urls=(),
        )


class DeviceStreamingTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_filler_only_recognition(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "嗯。"

        class RejectingConversation:
            async def reply(self, **_kwargs):
                raise AssertionError("Filler audio must not reach the conversation")

        callbacks = [AsyncMock() for _ in range(5)]
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=RejectingConversation(),
            speech=FakeStreamingSpeech(),
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        result = await turn.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 16000,
            request_id="device-filler",
            on_recognized=callbacks[0],
            on_tts_start=callbacks[1],
            on_sentence_start=callbacks[2],
            on_audio_packet=callbacks[3],
            on_tts_stop=callbacks[4],
        )

        self.assertEqual(result.user_text, "嗯。")
        self.assertEqual(result.reply, "")
        for callback in callbacks:
            callback.assert_not_awaited()

    async def test_uses_final_reply_when_no_stream_delta_is_available(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "用户问题"

        class NonStreamingConversation:
            async def reply(self, **kwargs):
                return DeviceTurnResult(
                    user_text=kwargs["user_text"],
                    reply="最终回复。",
                    audio_urls=(),
                )

        speech = FakeStreamingSpeech()
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=NonStreamingConversation(),
            speech=speech,
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        async def ignore(*_args):
            return None

        await turn.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 16000,
            request_id="device-1",
            on_recognized=ignore,
            on_tts_start=ignore,
            on_sentence_start=ignore,
            on_audio_packet=ignore,
            on_tts_stop=ignore,
        )

        self.assertEqual(speech.phrases, ["最终回复。"])

    async def test_streams_sentences_and_notifies_after_generation(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "用户问题"

        conversation = FakeStreamingConversation()
        speech = FakeStreamingSpeech()
        notifier = FakeStreamingNotifier()
        recognized = []
        lifecycle = []
        packets = []
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=conversation,
            speech=speech,
            notifier=notifier,
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        async def record(target, value):
            target.append(value)

        result = await turn.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 16000,
            request_id="device-1",
            on_recognized=lambda text: record(recognized, text),
            on_tts_start=lambda: record(lifecycle, "start"),
            on_sentence_start=lambda text: record(lifecycle, text),
            on_audio_packet=lambda packet: record(packets, packet),
            on_tts_stop=lambda: record(lifecycle, "stop"),
        )

        self.assertEqual(result.reply, "第一句。第二句")
        self.assertEqual(recognized, ["用户问题"])
        self.assertEqual(speech.phrases, ["第一句。第二句"])
        self.assertEqual(lifecycle[0], "start")
        self.assertEqual(lifecycle[-1], "stop")
        self.assertTrue(packets)
        self.assertEqual(notifier.user_id, "user-1")
        self.assertEqual(conversation.arguments[-1], False)

    async def test_rejects_internal_time_metadata_before_tts(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "用户问题"

        class LeakingConversation:
            async def reply(self, **kwargs):
                await kwargs["on_reply_delta"](
                    "[消息时间 2026-08-16T10:00:00+08:00]\n不该说出来。"
                )
                return DeviceTurnResult(
                    user_text=kwargs["user_text"],
                    reply="不该说出来。",
                    audio_urls=(),
                )

        speech = FakeStreamingSpeech()
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=LeakingConversation(),
            speech=speech,
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        async def ignore(*_args):
            return None

        with self.assertRaises(AgentDeliveryPlanError):
            await turn.execute(
                user_id="user-1",
                pcm16_audio=b"\x00\x00" * 16000,
                request_id="device-leak",
                on_recognized=ignore,
                on_tts_start=ignore,
                on_sentence_start=ignore,
                on_audio_packet=ignore,
                on_tts_stop=ignore,
            )

        self.assertEqual(speech.phrases, [])

    async def test_prefetches_next_phrase_while_first_phrase_is_streaming(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "用户问题"

        class CoordinatedSpeech:
            def __init__(self):
                self.first_finished = False
                self.second_started = asyncio.Event()
                self.second_started_before_first_finished = False

            async def _stream(self, text):
                if text == "第一段内容已经足够长了。":
                    await asyncio.wait_for(self.second_started.wait(), timeout=1)
                    yield b"\x00\x00" * 1440
                    self.first_finished = True
                    return
                self.second_started_before_first_finished = not self.first_finished
                self.second_started.set()
                yield b"\x00\x00" * 1440

            def stream_pcm16(self, text):
                return self._stream(text)

        class MultiPhraseConversation:
            async def reply(self, **kwargs):
                reply = "第一段内容已经足够长了。第二段内容也已经足够长。"
                await kwargs["on_reply_delta"](reply)
                return DeviceTurnResult(
                    user_text=kwargs["user_text"],
                    reply=reply,
                    audio_urls=(),
                )

        async def ignore(*_args):
            return None

        speech = CoordinatedSpeech()
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=MultiPhraseConversation(),
            speech=speech,
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
            prefetch_phrases=1,
        )

        await turn.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 16000,
            request_id="device-prefetch",
            on_recognized=ignore,
            on_tts_start=ignore,
            on_sentence_start=ignore,
            on_audio_packet=ignore,
            on_tts_stop=ignore,
        )

        self.assertTrue(speech.second_started_before_first_finished)

    async def test_progress_phrase_is_spoken_before_final_reply(self):
        class Recognizer:
            async def recognize_pcm16(self, audio):
                del audio
                return "今天有什么新闻"

        class ProgressConversation:
            async def reply(self, **kwargs):
                await kwargs["on_progress_text"]("好，我查一下。")
                await kwargs["on_reply_delta"]("今天比较受关注的是这件事。")
                return DeviceTurnResult(
                    user_text=kwargs["user_text"],
                    reply="今天比较受关注的是这件事。",
                    audio_urls=(),
                )

        speech = FakeStreamingSpeech()
        turn = StreamDeviceVoiceTurn(
            recognizer=Recognizer(),
            conversation=ProgressConversation(),
            speech=speech,
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=32,
            queue_max_packets=40,
        )

        async def ignore(*_args):
            return None

        await turn.execute(
            user_id="user-1",
            pcm16_audio=b"\x00\x00" * 16000,
            request_id="device-progress",
            on_recognized=ignore,
            on_tts_start=ignore,
            on_sentence_start=ignore,
            on_audio_packet=ignore,
            on_tts_stop=ignore,
        )

        self.assertEqual(
            speech.phrases,
            ["好，我查一下。", "今天比较受关注的是这件事。"],
        )

    async def test_retries_initial_tts_failure_once_and_releases_the_turn(self):
        class RetryOnceSpeech:
            def __init__(self):
                self.calls = 0

            async def _stream(self, text):
                del text
                self.calls += 1
                if self.calls == 1:
                    raise ValueError("rate limited")
                yield b"\x00\x00" * 1440

            def stream_pcm16(self, text):
                return self._stream(text)

        speech = RetryOnceSpeech()
        lifecycle = []
        turn = StreamDeviceVoiceTurn(
            recognizer=AsyncMock(return_value="用户问题"),
            conversation=FakeStreamingConversation(),
            speech=speech,
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        async def record(value=None):
            lifecycle.append(value)

        with patch(
            "features.devices.application.stream_voice_turn."
            "_TTS_EMPTY_AUDIO_RETRY_DELAY_SECONDS",
            0,
        ):
            await turn.execute(
                user_id="user-1",
                pcm16_audio=b"\x00\x00" * 16000,
                request_id="device-tts-retry",
                on_recognized=lambda _text: record("recognized"),
                on_tts_start=lambda: record("start"),
                on_sentence_start=lambda _text: record("sentence"),
                on_audio_packet=lambda _packet: record("packet"),
                on_tts_stop=lambda: record("stop"),
                recognized_text="用户问题",
            )

        self.assertEqual(speech.calls, 2)
        self.assertEqual(lifecycle.count("start"), 1)
        self.assertEqual(lifecycle.count("stop"), 1)

    async def test_tts_failure_after_audio_still_stops_exactly_once(self):
        class FailingAfterAudioSpeech:
            async def _stream(self, text):
                del text
                yield b"\x00\x00" * 1440
                raise ValueError("stream interrupted")

            def stream_pcm16(self, text):
                return self._stream(text)

        lifecycle = []
        turn = StreamDeviceVoiceTurn(
            recognizer=AsyncMock(return_value="用户问题"),
            conversation=FakeStreamingConversation(),
            speech=FailingAfterAudioSpeech(),
            notifier=FakeStreamingNotifier(),
            chunk_max_chars=24,
            queue_max_packets=40,
        )

        async def record(value=None):
            lifecycle.append(value)

        with self.assertRaisesRegex(ValueError, "stream interrupted"):
            await turn.execute(
                user_id="user-1",
                pcm16_audio=b"\x00\x00" * 16000,
                request_id="device-tts-failure",
                on_recognized=lambda _text: record("recognized"),
                on_tts_start=lambda: record("start"),
                on_sentence_start=lambda _text: record("sentence"),
                on_audio_packet=lambda _packet: record("packet"),
                on_tts_stop=lambda: record("stop"),
                recognized_text="用户问题",
            )

        self.assertEqual(lifecycle.count("start"), 1)
        self.assertEqual(lifecycle.count("stop"), 1)


class DeviceWebSocketTests(unittest.TestCase):
    def test_empty_realtime_asr_does_not_fall_back_to_batch(self):
        app = FastAPI()
        app.include_router(device_router.router)
        asr_session = FakeEmptyDeviceRealtimeAsrSession()
        stream_turn = FakeStreamingDeviceTurn()
        packets = _encode_pcm_packets(_sine_pcm(16000, 0.18), 16000)

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(device_router.settings, "echo_device_streaming_enabled", True),
            patch.object(device_router.settings, "echo_device_realtime_asr_enabled", True),
            patch.object(device_router.settings, "voice_streaming_asr_enabled", True),
            patch.object(
                device_router,
                "open_streaming_voice_recognition",
                new=AsyncMock(return_value=asr_session),
            ),
            patch.object(
                device_router,
                "get_stream_device_voice_turn",
                return_value=stream_turn,
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
            websocket.send_json({"type": "listen", "state": "start"})
            for packet in packets:
                websocket.send_bytes(packet)
            websocket.send_json({"type": "listen", "state": "stop"})

            self.assertEqual(websocket.receive_json()["state"], "stop")

        self.assertTrue(asr_session.finished)
        self.assertTrue(asr_session.closed)
        self.assertIsNone(stream_turn.recognized_text)

    def test_implausible_realtime_asr_falls_back_to_batch_recognition(self):
        app = FastAPI()
        app.include_router(device_router.router)
        asr_session = FakeImplausibleDeviceRealtimeAsrSession()
        stream_turn = FakeStreamingDeviceTurn()
        packets = _encode_pcm_packets(_sine_pcm(16000, 0.18), 16000)

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(device_router.settings, "echo_device_streaming_enabled", True),
            patch.object(device_router.settings, "echo_device_realtime_asr_enabled", True),
            patch.object(device_router.settings, "voice_streaming_asr_enabled", True),
            patch.object(
                device_router,
                "open_streaming_voice_recognition",
                new=AsyncMock(return_value=asr_session),
            ),
            patch.object(
                device_router,
                "get_stream_device_voice_turn",
                return_value=stream_turn,
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
            websocket.send_json({"type": "listen", "state": "start"})
            for packet in packets:
                websocket.send_bytes(packet)
            websocket.send_json({"type": "listen", "state": "stop"})

            self.assertEqual(websocket.receive_json()["text"], "batch-result")
            self.assertEqual(websocket.receive_json()["state"], "start")
            self.assertEqual(websocket.receive_json()["state"], "sentence_start")
            self.assertEqual(websocket.receive_bytes(), b"stream-opus")
            self.assertEqual(websocket.receive_json()["state"], "stop")

        self.assertTrue(asr_session.finished)
        self.assertTrue(asr_session.closed)
        self.assertIsNone(stream_turn.recognized_text)

    def test_realtime_asr_feeds_capture_and_passes_final_text_to_streaming_turn(self):
        app = FastAPI()
        app.include_router(device_router.router)
        asr_session = FakeDeviceRealtimeAsrSession()
        stream_turn = FakeStreamingDeviceTurn()
        packets = _encode_pcm_packets(_sine_pcm(16000, 0.18), 16000)

        with (
            patch.object(device_router.settings, "echo_device_token", "device-secret"),
            patch.object(
                device_router.settings,
                "echo_device_user_map_json",
                '{"aa:bb|client-1":"user-1"}',
            ),
            patch.object(device_router.settings, "echo_device_streaming_enabled", True),
            patch.object(device_router.settings, "echo_device_realtime_asr_enabled", True),
            patch.object(device_router.settings, "voice_streaming_asr_enabled", True),
            patch.object(
                device_router,
                "open_streaming_voice_recognition",
                new=AsyncMock(return_value=asr_session),
            ),
            patch.object(
                device_router,
                "get_stream_device_voice_turn",
                return_value=stream_turn,
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
            websocket.send_json({"type": "listen", "state": "start"})
            for packet in packets:
                websocket.send_bytes(packet)
            websocket.send_json({"type": "listen", "state": "stop"})

            stt = websocket.receive_json()
            self.assertEqual(stt["text"], "实时识别结果")
            self.assertEqual(websocket.receive_json()["state"], "start")
            self.assertEqual(websocket.receive_json()["state"], "sentence_start")
            self.assertEqual(websocket.receive_bytes(), b"stream-opus")
            self.assertEqual(websocket.receive_json()["state"], "stop")

        self.assertTrue(asr_session.audio)
        self.assertTrue(asr_session.finished)
        self.assertTrue(asr_session.closed)
        self.assertEqual(stream_turn.recognized_text, "实时识别结果")

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
