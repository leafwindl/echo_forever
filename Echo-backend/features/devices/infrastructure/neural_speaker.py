"""Client for the isolated model worker. No statistical fallback."""
import json
import math
import os
import urllib.error
import urllib.request


class SpeakerUnavailable(Exception):
    pass


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


def similarity(left, right):
    if not left or len(left) != len(right):
        return -1.0
    ln = math.sqrt(sum(v * v for v in left))
    rn = math.sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right)) / (ln * rn) if ln and rn else -1.0


def centroid(vectors):
    vector = [sum(column) / len(vectors) for column in zip(*vectors)]
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise ValueError("录入样本不一致，请重新录入")
    return [v / norm for v in vector]


def identify(
    vector,
    model_id,
    profiles,
    threshold=0.65,
    margin=0.12,
    *,
    diagnostics=False,
):
    # Provisional conservative gates, not accuracy claims or authorization.
    ranked = sorted(
        [(similarity(vector, p["embedding"]), p) for p in profiles
         if p["model_id"] == model_id and p["status"] == "active"],
        key=lambda item: item[0], reverse=True,
    )
    if not ranked:
        result = {"status": "unknown"}
        if diagnostics:
            result.update({
                "candidate_count": 0,
                "best_similarity": None,
            })
        return result
    best, profile = ranked[0]
    if best < threshold:
        result = {"status": "unknown"}
        if diagnostics:
            result.update({
                "candidate_count": len(ranked),
                "best_similarity": best,
            })
        return result
    if len(ranked) > 1 and best - ranked[1][0] < margin:
        result = {"status": "uncertain"}
        if diagnostics:
            result.update({
                "candidate_count": len(ranked),
                "best_similarity": best,
            })
        return result
    result = {"status": "matched", "person_id": profile["person_id"],
              "display_name": profile["display_name"], "similarity": best}
    if diagnostics:
        result.update({
            "candidate_count": len(ranked),
            "best_similarity": best,
        })
    return result
