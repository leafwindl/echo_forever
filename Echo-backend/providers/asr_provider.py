import asyncio
import base64
import concurrent.futures
import os
from typing import Protocol, cast

from shared.config import settings
from tencentcloud.asr.v20190614 import asr_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

from providers.registry import get_provider


class ASRProvider(Protocol):
    async def recognize(self, audio_path: str) -> str: ...


class TencentASRProvider:
    async def recognize(self, audio_path: str) -> str:
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError("无效的 audio_path")

        def sync_recognize():
            with open(audio_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            cred = credential.Credential(settings.tencent_secret_id, settings.tencent_secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "asr.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = asr_client.AsrClient(cred, "ap-shanghai", client_profile)

            req = models.SentenceRecognitionRequest()
            req.EngSerViceType = settings.tencent_asr_engine_model_type
            req.SourceType = 1
            req.VoiceFormat = "pcm"
            req.Data = audio_base64
            req.DataLen = len(audio_bytes)
            req.FilterModal = 0
            req.FilterPunc = 0
            req.ConvertNumMode = 1

            resp = client.SentenceRecognition(req)
            return str(resp.Result or "").strip()

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, sync_recognize)


def get_asr_provider() -> ASRProvider:
    return cast(ASRProvider, get_provider("asr", TencentASRProvider))
