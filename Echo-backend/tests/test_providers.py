import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import providers.tts_provider as tts_provider_module
from providers.embedding_provider import OpenAICompatibleEmbeddingProvider, get_embedding_provider
from providers.asr_provider import ASRProvider, get_asr_provider
from providers.registry import register_provider_factory, reset_provider_registry_for_tests
from providers.tts_provider import CosyVoiceTTSProvider, EdgeTTSProvider, get_tts_provider
from shared.config import settings


class FakeEmbeddingProvider:
    async def create_embedding(self, text, model=None):
        return [1.0, 2.0, 3.0]


class FakeTTSProvider:
    async def text_to_speech(self, text, voice_id):
        return f"{voice_id}:{text}".encode("utf-8")


class FakeASRProvider:
    async def recognize(self, audio_path):
        return f"recognized:{audio_path}"


class FakeCosyVoiceSynthesizer:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.cancelled = False
        self.__class__.instances.append(self)

    def streaming_call(self, text):
        self.text = text
        self.callback.on_data(b"audio-1")

    def streaming_complete(self):
        self.callback.on_data(b"audio-2")
        self.callback.on_complete()

    def streaming_cancel(self, _timeout_millis=1000):
        self.cancelled = True

    def get_last_request_id(self):
        return "request-test"

    def get_first_package_delay(self):
        return 123


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        reset_provider_registry_for_tests()
        FakeCosyVoiceSynthesizer.instances.clear()

    async def test_embedding_provider_rejects_empty_text(self):
        provider = OpenAICompatibleEmbeddingProvider()

        with self.assertRaises(ValueError):
            await provider.create_embedding("   ")

    async def test_tts_provider_rejects_empty_text(self):
        provider = EdgeTTSProvider()

        with self.assertRaises(ValueError):
            await provider.text_to_speech("   ", "zh-CN-XiaoxiaoNeural")

    async def test_cosyvoice_provider_streams_sdk_audio(self):
        provider = CosyVoiceTTSProvider()
        fake_dashscope = SimpleNamespace(api_key=None)

        with (
            patch.object(tts_provider_module, "SpeechSynthesizer", FakeCosyVoiceSynthesizer),
            patch.object(tts_provider_module, "dashscope", fake_dashscope),
            patch.object(settings, "dashscope_api_key", "test-key"),
            patch.object(settings, "dashscope_workspace_id", "workspace-a"),
            patch.object(settings, "cosyvoice_model", "cosyvoice-v3.5-flash"),
            patch.object(settings, "cosyvoice_websocket_url", ""),
            patch.object(settings, "cosyvoice_instruction", "温柔自然地说话"),
        ):
            result = await provider.text_to_speech("你好", "custom-voice")

        self.assertEqual(result.audio_bytes, b"audio-1audio-2")
        self.assertEqual(result.content_type, "audio/mpeg")
        self.assertEqual(fake_dashscope.api_key, "test-key")
        synthesizer = FakeCosyVoiceSynthesizer.instances[0]
        self.assertEqual(synthesizer.text, "你好")
        self.assertEqual(synthesizer.kwargs["model"], "cosyvoice-v3.5-flash")
        self.assertEqual(synthesizer.kwargs["voice"], "custom-voice")
        self.assertEqual(synthesizer.kwargs["instruction"], "温柔自然地说话")
        self.assertEqual(
            synthesizer.kwargs["url"],
            "wss://workspace-a.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference",
        )

    async def test_cosyvoice_provider_reports_missing_credentials(self):
        provider = CosyVoiceTTSProvider()

        with (
            patch.object(settings, "dashscope_api_key", ""),
            patch.object(settings, "dashscope_workspace_id", ""),
            patch.object(settings, "cosyvoice_websocket_url", ""),
            patch.object(settings, "cosyvoice_model", "cosyvoice-v3.5-flash"),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "DASHSCOPE_API_KEY, DASHSCOPE_WORKSPACE_ID, TTS_VOICE_ID",
            ):
                await provider.text_to_speech("你好", "")

    async def test_get_tts_provider_supports_cosyvoice(self):
        with patch.object(settings, "tts_provider", "cosyvoice"):
            provider = get_tts_provider()

        self.assertIsInstance(provider, CosyVoiceTTSProvider)

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
