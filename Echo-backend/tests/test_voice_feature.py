import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.voice.application.use_cases import GenerateVoiceReply, RecognizeVoice
from features.voice.domain.entities import UnsupportedVoiceFormatError
from features.voice.infrastructure.audio_storage import cleanup_expired_audio_files_in_dir


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


class FakeChatResponder:
    async def reply(self, user_id, message):
        return f"reply:{user_id}:{message}"


class FakeSynthesizer:
    async def synthesize(self, text):
        return f"audio:{text}".encode("utf-8")


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

    async def test_generate_voice_reply_uses_chat_tts_and_storage(self):
        storage = FakeAudioStorage()
        use_case = GenerateVoiceReply(
            chat_responder=FakeChatResponder(),
            synthesizer=FakeSynthesizer(),
            audio_storage=storage,
        )

        result = await use_case.execute("user_a", "hello")

        self.assertEqual(result.reply, "reply:user_a:hello")
        self.assertEqual(result.audio_url, "http://example.test/audio.mp3")
        self.assertEqual(storage.generated_audio, [b"audio:reply:user_a:hello"])

    async def test_cleanup_expired_audio_files_deletes_only_expired_mp3_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir)
            expired_audio = storage_dir / "expired.mp3"
            fresh_audio = storage_dir / "fresh.mp3"
            ignored_text = storage_dir / "expired.txt"
            expired_audio.write_bytes(b"old-audio")
            fresh_audio.write_bytes(b"fresh-audio")
            ignored_text.write_text("ignore", encoding="utf-8")

            expired_audio_mtime = 100.0
            fresh_audio_mtime = 190.0
            expired_audio.touch()
            fresh_audio.touch()
            ignored_text.touch()
            import os

            os.utime(expired_audio, (expired_audio_mtime, expired_audio_mtime))
            os.utime(fresh_audio, (fresh_audio_mtime, fresh_audio_mtime))
            os.utime(ignored_text, (expired_audio_mtime, expired_audio_mtime))

            result = cleanup_expired_audio_files_in_dir(
                directory=storage_dir,
                retention_seconds=50,
                batch_size=10,
                now=200.0,
            )

            self.assertEqual(result.deleted, 1)
            self.assertEqual(result.released_bytes, len(b"old-audio"))
            self.assertFalse(expired_audio.exists())
            self.assertTrue(fresh_audio.exists())
            self.assertTrue(ignored_text.exists())


if __name__ == "__main__":
    unittest.main()
