"""Short-lived, single-device calibration. Raw audio is never retained."""
import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from features.devices.infrastructure.neural_speaker import (
    SpeakerUnavailable, centroid, similarity,
)

logger = logging.getLogger(__name__)

PROMPTS = (
    "今天我想和 Echo 聊聊最近发生的一件开心的事情。",
    "平时我喜欢听音乐，也喜欢和家人朋友一起散步。",
    "希望每天都能发现一些新的、有意思的事情。",
    "周末有空的时候，我想给自己安排一次轻松的旅行。",
)


@dataclass
class Calibration:
    session_id: str
    owner_id: str
    device_id: str
    person_id: str
    name: str
    expires: float
    samples: list = field(default_factory=list)
    hashes: set = field(default_factory=set)
    model_id: str = ""
    busy: bool = False
    error: str = ""

    def view(self):
        count = len(self.samples)
        return {
            "session_id": self.session_id,
            "person_id": self.person_id,
            "display_name": self.name,
            "sample_count": count,
            "state": "verifying" if count == 3 else "collecting",
            "prompt": PROMPTS[count],
            "error": self.error,
        }


class SpeakerCalibration:
    def __init__(self, save, clock=time.monotonic):
        self.save = save
        self.clock = clock
        self.sessions = {}
        self.lock = threading.RLock()

    def _prune(self):
        for key, session in list(self.sessions.items()):
            if session.expires <= self.clock():
                self.sessions.pop(key, None)

    def start(self, owner_id, device_id, person_id, name):
        with self.lock:
            self._prune()
            if device_id in self.sessions:
                raise ValueError("设备正在校准，请先取消当前会话")
            session = Calibration(uuid.uuid4().hex, owner_id, device_id, person_id,
                                  name, self.clock() + 600)
            self.sessions[device_id] = session
            return session.view()

    def pending(self, owner_id, device_id):
        with self.lock:
            self._prune()
            session = self.sessions.get(device_id)
            return session.view() if session and session.owner_id == owner_id else None

    def cancel(self, owner_id, device_id, session_id=None):
        with self.lock:
            session = self.sessions.get(device_id)
            if session and session.owner_id == owner_id and (
                session_id is None or session.session_id == session_id
            ):
                self.sessions.pop(device_id, None)

    def active(self, owner_id, device_id):
        return self.pending(owner_id, device_id) is not None

    def consume(self, owner_id, device_id, audio, extract):
        with self.lock:
            self._prune()
            session = self.sessions.get(device_id)
            if session is None or session.owner_id != owner_id:
                return None
            if session.busy:
                return "正在处理上一段，请稍等"
            session.busy = True
            session.error = ""
            token = session.session_id
        try:
            digest = hashlib.sha256(audio).hexdigest()
            if digest in session.hashes:
                raise ValueError("这段录音已提交，请读下一句")
            vector, model_id = extract(audio)
            with self.lock:
                if self.sessions.get(device_id) is not session or session.session_id != token:
                    return None
                if session.model_id and session.model_id != model_id:
                    raise ValueError("声纹模型已变更，请重新开始校准")
                if session.samples and similarity(centroid(session.samples), vector) < 0.65:
                    raise ValueError("声音与本次硬件样本不一致，请由同一人重读")
                if len(session.samples) == 3:
                    self.save(session, vector, model_id)
                    self.sessions.pop(device_id, None)
                    return f"{session.name}的硬件声纹已通过独立验证"
                session.samples.append(vector)
                session.hashes.add(digest)
                session.model_id = model_id
                session.expires = self.clock() + 600
                return f"第{len(session.samples)}段已保存，请看 App 读下一句"
        except (ValueError, SpeakerUnavailable) as exc:
            with self.lock:
                if self.sessions.get(device_id) is session:
                    session.error = str(exc)
            return f"本段未通过：{exc}"
        except Exception:
            logger.exception("Hardware speaker calibration failed device_id=%s", device_id)
            with self.lock:
                if self.sessions.get(device_id) is session:
                    session.error = "校准服务暂不可用，请重试本段"
            return "本段未保存：校准服务暂不可用，请重试"
        finally:
            with self.lock:
                session.busy = False
