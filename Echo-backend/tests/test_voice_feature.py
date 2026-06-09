import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.voice.application.use_cases import GenerateVoiceReply, RecognizeVoice
from features.voice.domain.entities import UnsupportedVoiceFormatError


class FakeAudioStorage:
    def __init__(self):
        self.saved_uploads = []
        self.generated_audio = []

    def save_upload(self, audio_bytes, suffix=".mp3"):
        self.saved_uploads.append((audio_bytes, suffix))
        return "fake_upload.mp3"

    async def save_generated_audio(self, audio_bytes):
        self.generated_audio.append(audio_bytes)
        return "http://example.test/audio.mp3"


class FakeRecognizer:
    async def recognize(self, audio_path):
        return f"recognized:{audio_path}"


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


if __name__ == "__main__":
    unittest.main()
