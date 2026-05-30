import asyncio
import time
import base64
import os
import re
import concurrent.futures
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.asr.v20190614 import asr_client, models
from config import settings

async def recognize_audio(audio_path: str) -> str:
    """
    使用腾讯云录音文件识别，直接读取文件转换为 base64 发送。
    返回识别后的文本。
    """
    if not audio_path or not os.path.exists(audio_path):
        raise ValueError("无效的 audio_path")

    def sync_recognize():
        # 读取本地文件并转为 Base64
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        cred = credential.Credential(settings.tencent_secret_id, settings.tencent_secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = asr_client.AsrClient(cred, "ap-shanghai", client_profile)

        req = models.CreateRecTaskRequest()
        req.EngineModelType = "16k_zh"      # 采样率16kHz，中文通用
        req.ChannelNum = 1                  # 单声道
        req.ResTextFormat = 0               # 识别结果文本（不带标点）
        req.SourceType = 1                  # 1 表示数据（Base64 字符串）
        req.Data = audio_base64
        req.DataLen = len(audio_bytes)

        resp = client.CreateRecTask(req)
        task_id = resp.Data.TaskId

        # 轮询结果，每2秒一次，最长等待60秒
        for _ in range(30):
            time.sleep(2)
            req2 = models.DescribeTaskStatusRequest()
            req2.TaskId = task_id
            resp2 = client.DescribeTaskStatus(req2)
            if resp2.Data.Status == 2:          # 成功
                # 腾讯云返回的有时会带有时间戳，形如 [0:0.740,0:3410] 你好啊，使用正则去除这些时间戳
                clean_result = re.sub(r'\[.*?\]\s*', '', resp2.Data.Result)
                return clean_result.strip()
            elif resp2.Data.Status == 3:        # 失败
                raise Exception(f"ASR failed: {resp2.Data.ErrorMsg}")
        raise TimeoutError("ASR task timeout")

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, sync_recognize)
    return result