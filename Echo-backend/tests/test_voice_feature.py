import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.voice.application.use_cases import (
    OpenStreamingVoiceRecognition,
    RecognizeVoice,
    SynthesizeVoiceReply,
)
from features.voice.domain.entities import SynthesizedVoiceAudio, UnsupportedVoiceFormatError
from features.voice.domain.segmentation import sanitize_text_for_speech, split_text_for_speech
from features.voice.infrastructure.audio_storage import cleanup_expired_audio_files_in_dir
from features.voice.infrastructure.streaming_asr import (
    FunASRTranscriptAccumulator,
    TencentASRTranscriptAccumulator,
)


class FakeAudioStorage:
    def __init__(self):
        self.saved_uploads = []
        self.generated_audio = []
        self.deleted_uploads = []

    def save_upload(self, audio_bytes, suffix=".mp3"):
        self.saved_uploads.append((audio_bytes, suffix))
        return "fake_upload.mp3"

    def delete_upload(self, audio_path):
        self.deleted_uploads.append(audio_path)

    async def save_generated_audio(self, audio_bytes):
        self.generated_audio.append(audio_bytes)
        return "http://example.test/audio.mp3"


class FakeRecognizer:
    async def recognize(self, audio_path):
        return f"recognized:{audio_path}"


class FailingRecognizer:
    async def recognize(self, audio_path):
        raise RuntimeError(f"recognize failed:{audio_path}")


class FakeSynthesizer:
    async def synthesize(self, text):
        return f"audio:{text}".encode("utf-8")


class FailingSynthesizer:
    async def synthesize(self, text):
        raise RuntimeError(f"synthesize failed:{text}")


class FakeStructuredSynthesizer:
    def __init__(self):
        self.segments = []

    async def synthesize(self, text):
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

        result = await use_case.execute(b"mp3-bytes", "audio/mp3")

        self.assertEqual(result.user_text, "recognized:fake_upload.mp3")
        self.assertEqual(storage.saved_uploads, [(b"mp3-bytes", ".mp3")])
        self.assertEqual(storage.deleted_uploads, ["fake_upload.mp3"])

    async def test_recognize_voice_deletes_upload_when_recognizer_fails(self):
        storage = FakeAudioStorage()
        use_case = RecognizeVoice(audio_storage=storage, recognizer=FailingRecognizer())

        with self.assertRaises(RuntimeError):
            await use_case.execute(b"mp3-bytes", "audio/mp3")

        self.assertEqual(storage.deleted_uploads, ["fake_upload.mp3"])

    async def test_recognize_voice_rejects_unsupported_content_type(self):
        use_case = RecognizeVoice(audio_storage=FakeAudioStorage(), recognizer=FakeRecognizer())

        with self.assertRaises(UnsupportedVoiceFormatError):
            await use_case.execute(b"wav-bytes", "audio/wav")

    async def test_synthesize_voice_reply_stores_generated_audio(self):
        storage = FakeAudioStorage()
        use_case = SynthesizeVoiceReply(
            synthesizer=FakeSynthesizer(),
            audio_storage=storage,
        )

        result = await use_case.execute("hello")

        self.assertEqual(result.audio_urls, ("http://example.test/audio.mp3",))
        self.assertEqual(storage.generated_audio, [b"audio:hello"])

    async def test_synthesize_voice_reply_rejects_empty_text(self):
        use_case = SynthesizeVoiceReply(
            synthesizer=FakeSynthesizer(),
            audio_storage=FakeAudioStorage(),
        )

        with self.assertRaises(ValueError):
            await use_case.execute("   ")

    async def test_synthesize_voice_reply_splits_and_stores_wav_segments(self):
        storage = FakeStructuredAudioStorage()
        synthesizer = FakeStructuredSynthesizer()
        use_case = SynthesizeVoiceReply(
            synthesizer=synthesizer,
            audio_storage=storage,
            segment_max_chars=8,
            reply_max_chars=100,
        )

        result = await use_case.execute("第一句话。第二句话！")

        self.assertEqual(synthesizer.segments, ["第一句话。", "第二句话！"])
        self.assertEqual(
            result.audio_urls,
            (
                "http://example.test/audio-1.wav",
                "http://example.test/audio-2.wav",
            ),
        )
        self.assertEqual([suffix for _, suffix in storage.generated_audio], [".wav", ".wav"])

    async def test_open_streaming_voice_recognition_returns_provider_session(self):
        session = FakeStreamingSession()
        use_case = OpenStreamingVoiceRecognition(FakeStreamingRecognizer(session))

        result = await use_case.execute()

        self.assertIs(result, session)

    def test_split_text_for_speech_enforces_segment_and_total_limits(self):
        segments = split_text_for_speech(
            "abcdefghij。后面的内容不会全部进入合成。",
            max_chars=4,
            total_max_chars=14,
        )

        self.assertTrue(segments)
        self.assertTrue(all(len(segment) <= 4 for segment in segments))
        self.assertLessEqual(sum(len(segment) for segment in segments), 14)

    def test_sanitize_text_for_speech_removes_visual_only_unicode(self):
        self.assertEqual(
            sanitize_text_for_speech("我在听。🌿\u200d✨"),
            "我在听。",
        )

    def test_split_text_for_speech_omits_emoji_only_segment(self):
        self.assertEqual(
            split_text_for_speech("第一句话。🌿", max_chars=80, total_max_chars=100),
            ("第一句话。",),
        )

    def test_funasr_accumulator_does_not_finish_on_intermediate_offline_segment(self):
        accumulator = FunASRTranscriptAccumulator()

        online = accumulator.apply({"mode": "2pass-online", "text": "你号"})
        corrected = accumulator.apply(
            {"mode": "2pass-offline", "text": "你好。", "is_final": False}
        )
        next_online = accumulator.apply({"mode": "2pass-online", "text": "今"})
        final = accumulator.apply(
            {"mode": "2pass-offline", "text": "今天很好。", "is_final": True}
        )

        self.assertEqual(online.text, "你号")
        self.assertEqual(corrected.text, "你好。")
        self.assertFalse(corrected.is_final)
        self.assertEqual(next_online.text, "你好。今")
        self.assertEqual(final.text, "你好。今天很好。")
        self.assertTrue(final.is_final)

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


if __name__ == "__main__":
    unittest.main()
