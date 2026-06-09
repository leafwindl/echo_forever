import asyncio
import base64
import concurrent.futures
import os
import re
import time
from typing import Protocol, cast

from tencentcloud.asr.v20190614 import asr_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

from providers.registry import get_provider
from shared.config import settings


class ASRProvider(Protocol):
    async def recognize(self, audio_path: str) -> str:
        ...


class TencentASRProvider:
    async def recognize(self, audio_path: str) -> str:
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError("无效的 audio_path")

        def sync_recognize():
            audio_bytes = open(audio_path, "rb").read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            cred = credential.Credential(settings.tencent_secret_id, settings.tencent_secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "asr.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = asr_client.AsrClient(cred, "ap-shanghai", client_profile)

            req = models.CreateRecTaskRequest()
            req.EngineModelType = "16k_zh"
            req.ChannelNum = 1
            req.ResTextFormat = 0
            req.SourceType = 1
            req.Data = audio_base64
            req.DataLen = len(audio_bytes)

            resp = client.CreateRecTask(req)
            task_id = resp.Data.TaskId

            for _ in range(30):
                time.sleep(2)
                req2 = models.DescribeTaskStatusRequest()
                req2.TaskId = task_id
                resp2 = client.DescribeTaskStatus(req2)
                if resp2.Data.Status == 2:
                    clean_result = re.sub(r"\[.*?\]\s*", "", resp2.Data.Result)
                    return clean_result.strip()
                if resp2.Data.Status == 3:
                    raise RuntimeError(f"ASR failed: {resp2.Data.ErrorMsg}")
            raise TimeoutError("ASR task timeout")

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, sync_recognize)


def get_asr_provider() -> ASRProvider:
    return cast(ASRProvider, get_provider("asr", TencentASRProvider))
