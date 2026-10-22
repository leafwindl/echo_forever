"""Client for the isolated model worker. No statistical fallback."""
import json
import math
import os
import urllib.error
import urllib.request

from features.devices.domain.speaker_vectors import SpeakerUnavailable




def extract(audio: bytes) -> tuple[list[float], str]:
    base = os.environ.get("ECHO_SPEAKER_SERVICE_URL", "").rstrip("/")
    if not base:
        raise SpeakerUnavailable("声纹模型尚未启动")
    request = urllib.request.Request(
        base + "/embedding", data=audio,
        headers={"Content-Type": "application/octet-stream"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (413, 422):
            raise ValueError(json.loads(error.read()).get("detail", "录音不符合要求")) from error
        raise SpeakerUnavailable("声纹服务忙碌或暂不可用") from error
    except (OSError, ValueError) as error:
        raise SpeakerUnavailable("声纹服务暂不可用，请稍后重试") from error
    vector = result.get("embedding")
    model_id = result.get("model_id")
    if (
        not isinstance(vector, list) or not 32 <= len(vector) <= 2048
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector)
        or not isinstance(model_id, str) or not model_id.startswith("campp-zh:")
    ):
        raise SpeakerUnavailable("声纹模型返回格式不正确")
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise SpeakerUnavailable("声纹特征无效")
    return [v / norm for v in vector], model_id
