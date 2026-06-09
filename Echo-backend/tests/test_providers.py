import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.embedding_provider import OpenAICompatibleEmbeddingProvider, get_embedding_provider
from providers.asr_provider import ASRProvider, get_asr_provider
from providers.registry import register_provider_factory, reset_provider_registry_for_tests
from providers.tts_provider import EdgeTTSProvider, get_tts_provider


class FakeEmbeddingProvider:
    async def create_embedding(self, text, model=None):
        return [1.0, 2.0, 3.0]


class FakeTTSProvider:
    async def text_to_speech(self, text, voice_id):
        return f"{voice_id}:{text}".encode("utf-8")


class FakeASRProvider:
    async def recognize(self, audio_path):
        return f"recognized:{audio_path}"


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        reset_provider_registry_for_tests()

    async def test_embedding_provider_rejects_empty_text(self):
        provider = OpenAICompatibleEmbeddingProvider()

        with self.assertRaises(ValueError):
            await provider.create_embedding("   ")

    async def test_tts_provider_rejects_empty_text(self):
        provider = EdgeTTSProvider()

        with self.assertRaises(ValueError):
            await provider.text_to_speech("   ", "zh-CN-XiaoxiaoNeural")

    async def test_registry_can_replace_embedding_provider(self):
        fake_provider = FakeEmbeddingProvider()
        register_provider_factory("embedding", lambda: fake_provider)

        provider = get_embedding_provider()
        embedding = await provider.create_embedding("hello")

        self.assertIs(provider, fake_provider)
        self.assertEqual(embedding, [1.0, 2.0, 3.0])

    async def test_registry_can_replace_tts_provider(self):
        fake_provider = FakeTTSProvider()
        register_provider_factory("tts", lambda: fake_provider)

        provider = get_tts_provider()
        audio = await provider.text_to_speech("hello", "voice_a")

        self.assertIs(provider, fake_provider)
        self.assertEqual(audio, b"voice_a:hello")

    async def test_registry_can_replace_asr_provider(self):
        fake_provider = FakeASRProvider()
        register_provider_factory("asr", lambda: fake_provider)

        provider: ASRProvider = get_asr_provider()
        text = await provider.recognize("audio.mp3")

        self.assertIs(provider, fake_provider)
        self.assertEqual(text, "recognized:audio.mp3")


if __name__ == "__main__":
    unittest.main()
