import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.voice.application.use_cases import (
    OpenStreamingVoiceRecognition,
    RecognizeVoice,
    SynthesizeVoiceReply,
)
from features.voice.domain.entities import SynthesizedVoiceAudio, UnsupportedVoiceFormatError
from features.voice.domain.speech_delivery import prepare_speech_text
from features.voice.infrastructure.audio_storage import (
    cleanup_expired_audio_files_in_dir,
    save_upload_audio_file,
)
from features.voice.infrastructure.streaming_asr import (
    TencentASRTranscriptAccumulator,
    build_tencent_asr_websocket_url,
)
from shared.config import settings


class FakeAudioStorage:
    def __init__(self):
        self.saved_uploads = []
        self.generated_audio = []
        self.deleted_uploads = []

    def save_upload(self, audio_bytes, suffix=".pcm"):
        self.saved_uploads.append((audio_bytes, suffix))
        return "fake_upload.pcm"

    def delete_upload(self, audio_path):
        self.deleted_uploads.append(audio_path)

    async def save_generated_audio(self, audio_bytes, suffix=".mp3"):
        self.generated_audio.append((audio_bytes, suffix))
        return "http://example.test/audio.mp3"


class FakeRecognizer:
    async def recognize(self, audio_path):
        return f"recognized:{audio_path}"


class FailingRecognizer:
    async def recognize(self, audio_path):
        raise RuntimeError(f"recognize failed:{audio_path}")


class FakeSynthesizer:
    def __init__(self):
        self.requests = []

    async def synthesize(self, text, instruction=None):
        self.requests.append((text, instruction))
        return SynthesizedVoiceAudio(
            audio_bytes=f"audio:{text}".encode(),
            file_suffix=".mp3",
            content_type="audio/mpeg",
        )


class FailingSynthesizer:
    async def synthesize(self, text, instruction=None):
        del instruction
        raise RuntimeError(f"synthesize failed:{text}")


class FakeStructuredSynthesizer:
    def __init__(self):
        self.segments = []

    async def synthesize(self, text, instruction=None):
        del instruction
        self.segments.append(text)
        return SynthesizedVoiceAudio(
            audio_bytes=f"wav:{text}".encode(),
            file_suffix=".wav",
            content_type="audio/wav",
        )


class FakeStructuredAudioStorage(FakeAudioStorage):
    async def save_generated_audio(self, audio_bytes, suffix=".mp3"):
        self.generated_audio.append((audio_bytes, suffix))
        return f"http://example.test/audio-{len(self.generated_audio)}{suffix}"


class FakeStreamingSession:
    pass


class FakeStreamingRecognizer:
    def __init__(self, session):
        self.session = session

    async def open_session(self):
        return self.session


class VoiceFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognize_voice_saves_upload_and_calls_recognizer(self):
        storage = FakeAudioStorage()
        use_case = RecognizeVoice(audio_storage=storage, recognizer=FakeRecognizer())

        result = await use_case.execute(b"\x01\x02\x03\x04", "audio/L16")

        self.assertEqual(result.user_text, "recognized:fake_upload.pcm")
        self.assertEqual(storage.saved_uploads, [(b"\x01\x02\x03\x04", ".pcm")])
        self.assertEqual(storage.deleted_uploads, ["fake_upload.pcm"])

    async def test_recognize_voice_deletes_upload_when_recognizer_fails(self):
        storage = FakeAudioStorage()
        use_case = RecognizeVoice(audio_storage=storage, recognizer=FailingRecognizer())

        with self.assertRaises(RuntimeError):
            await use_case.execute(b"\x01\x02", "audio/L16")

        self.assertEqual(storage.deleted_uploads, ["fake_upload.pcm"])

    async def test_recognize_voice_rejects_unsupported_content_type(self):
        use_case = RecognizeVoice(audio_storage=FakeAudioStorage(), recognizer=FakeRecognizer())

        with self.assertRaises(UnsupportedVoiceFormatError):
            await use_case.execute(b"wav-bytes", "audio/wav")

    async def test_recognize_voice_accepts_pcm_content_type_parameters(self):
        storage = FakeAudioStorage()
        use_case = RecognizeVoice(audio_storage=storage, recognizer=FakeRecognizer())

        await use_case.execute(
            b"\x01\x02",
            "audio/L16; rate=16000; channels=1",
        )

        self.assertEqual(storage.saved_uploads, [(b"\x01\x02", ".pcm")])

    async def test_recognize_voice_rejects_incomplete_pcm16_sample(self):
        use_case = RecognizeVoice(audio_storage=FakeAudioStorage(), recognizer=FakeRecognizer())

        with self.assertRaisesRegex(ValueError, "complete 16-bit samples"):
            await use_case.execute(b"\x01", "audio/L16")

    async def test_synthesize_voice_reply_stores_generated_audio(self):
        storage = FakeAudioStorage()
        use_case = SynthesizeVoiceReply(
            synthesizer=FakeSynthesizer(),
            audio_storage=storage,
        )

        result = await use_case.execute("hello")

        self.assertEqual(result.audio_urls, ("http://example.test/audio.mp3",))
        self.assertEqual(storage.generated_audio, [(b"audio:hello", ".mp3")])
        self.assertEqual(len(use_case.synthesizer.requests), 1)
        self.assertIsNone(use_case.synthesizer.requests[0][1])

    async def test_synthesize_voice_reply_rejects_empty_text(self):
        use_case = SynthesizeVoiceReply(
            synthesizer=FakeSynthesizer(),
            audio_storage=FakeAudioStorage(),
        )

        with self.assertRaises(ValueError):
            await use_case.execute("   ")

    async def test_synthesize_voice_reply_uses_one_request_and_stores_one_wav(self):
        storage = FakeStructuredAudioStorage()
        synthesizer = FakeStructuredSynthesizer()
        use_case = SynthesizeVoiceReply(
            synthesizer=synthesizer,
            audio_storage=storage,
            reply_max_chars=100,
        )

        result = await use_case.execute("第一句话。第二句话！")

        self.assertEqual(synthesizer.segments, ["第一句话。第二句话！"])
        self.assertEqual(result.audio_urls, ("http://example.test/audio-1.wav",))
        self.assertEqual([suffix for _, suffix in storage.generated_audio], [".wav"])

    async def test_open_streaming_voice_recognition_returns_provider_session(self):
        session = FakeStreamingSession()
        use_case = OpenStreamingVoiceRecognition(FakeStreamingRecognizer(session))

        result = await use_case.execute()

        self.assertIs(result, session)

    def test_prepare_speech_text_applies_total_limit_without_segmenting(self):
        text = prepare_speech_text("abcdefghij。后面的内容不会全部进入合成。", maximum_chars=14)

        self.assertEqual(text, "abcdefghij。后面的")

    def test_prepare_speech_text_removes_visual_only_unicode(self):
        self.assertEqual(
            prepare_speech_text("我在听。🌿\u200d✨", maximum_chars=100),
            "我在听。",
        )

    def test_tencent_accumulator_replaces_partial_and_keeps_stable_segments(self):
        accumulator = TencentASRTranscriptAccumulator()

        first_partial = accumulator.apply(
            {"result": {"index": 0, "slice_type": 1, "voice_text_str": "你号"}}
        )
        first_stable = accumulator.apply(
            {"result": {"index": 0, "slice_type": 2, "voice_text_str": "你好。"}}
        )
        second_partial = accumulator.apply(
            {"result": {"index": 1, "slice_type": 1, "voice_text_str": "今天"}}
        )
        final = accumulator.apply({"final": 1})

        self.assertEqual(first_partial.text, "你号")
        self.assertEqual(first_stable.text, "你好。")
        self.assertEqual(second_partial.text, "你好。今天")
        self.assertEqual(final.text, "你好。今天")
        self.assertTrue(final.is_final)

    def test_tencent_streaming_url_declares_pcm_audio(self):
        with (
            patch.object(settings, "tencent_app_id", "123456"),
            patch.object(settings, "tencent_secret_id", "secret-id"),
            patch.object(settings, "tencent_secret_key", "secret-key"),
        ):
            url = build_tencent_asr_websocket_url("voice-id", now=1_700_000_000)

        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["voice_format"], ["1"])
        self.assertEqual(query["engine_model_type"], [settings.tencent_asr_engine_model_type])

    async def test_cleanup_expired_audio_files_deletes_expired_supported_audio_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir)
            expired_audio = storage_dir / "expired.mp3"
            fresh_audio = storage_dir / "fresh.mp3"
            expired_wav = storage_dir / "expired.wav"
            ignored_text = storage_dir / "expired.txt"
            expired_audio.write_bytes(b"old-audio")
            fresh_audio.write_bytes(b"fresh-audio")
            expired_wav.write_bytes(b"old-wav")
            ignored_text.write_text("ignore", encoding="utf-8")

            expired_audio_mtime = 100.0
            fresh_audio_mtime = 190.0
            expired_audio.touch()
            fresh_audio.touch()
            expired_wav.touch()
            ignored_text.touch()
            import os

            os.utime(expired_audio, (expired_audio_mtime, expired_audio_mtime))
            os.utime(fresh_audio, (fresh_audio_mtime, fresh_audio_mtime))
            os.utime(expired_wav, (expired_audio_mtime, expired_audio_mtime))
            os.utime(ignored_text, (expired_audio_mtime, expired_audio_mtime))

            result = cleanup_expired_audio_files_in_dir(
                directory=storage_dir,
                retention_seconds=50,
                batch_size=10,
                now=200.0,
            )

            self.assertEqual(result.deleted, 2)
            self.assertEqual(result.released_bytes, len(b"old-audio") + len(b"old-wav"))
            self.assertFalse(expired_audio.exists())
            self.assertTrue(fresh_audio.exists())
            self.assertFalse(expired_wav.exists())
            self.assertTrue(ignored_text.exists())

    def test_upload_storage_keeps_pcm_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir)
            with patch(
                "features.voice.infrastructure.audio_storage.get_voice_upload_dir",
                return_value=storage_dir,
            ):
                audio_path = save_upload_audio_file(b"\x01\x02", suffix=".pcm")

            self.assertEqual(Path(audio_path).suffix, ".pcm")
            self.assertEqual(Path(audio_path).read_bytes(), b"\x01\x02")

    def test_upload_storage_rejects_non_pcm_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "features.voice.infrastructure.audio_storage.get_voice_upload_dir",
            return_value=Path(temp_dir),
        ), self.assertRaisesRegex(ValueError, r"must use the \.pcm suffix"):
            save_upload_audio_file(b"\x01\x02", suffix=".mp3")

    def test_pcm_cleanup_can_target_upload_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir)
            expired_pcm = storage_dir / "expired.pcm"
            expired_pcm.write_bytes(b"old-pcm")
            expired_pcm.touch()
            import os

            os.utime(expired_pcm, (100.0, 100.0))

            result = cleanup_expired_audio_files_in_dir(
                directory=storage_dir,
                retention_seconds=50,
                batch_size=10,
                now=200.0,
                patterns=("*.pcm",),
            )

            self.assertEqual(result.deleted, 1)
            self.assertFalse(expired_pcm.exists())


if __name__ == "__main__":
    unittest.main()
