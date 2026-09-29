"""Explicit voice enrollment, bounded to one expiring session per device.

The local backend uses one worker. Sessions intentionally expire on restart and
must never silently resume recording after a reconnect or expired approval.
"""
import re
import time
import uuid
from dataclasses import dataclass


PROMPTS = (
    "今天我想和你聊聊最近发生的一件开心的事情。",
    "我平时喜欢听音乐，也喜欢和家人朋友一起散步。",
    "我希望每天都能发现一些新的、有意思的事情。",
    "周末有空的时候，我想给自己安排一次轻松的旅行。",
)


def clean(text):
    return re.sub(r"[\s，。！？,.!?、]", "", text).lower()


@dataclass
class EnrollmentSession:
    session_id: str
    owner_id: str
    device_id: str
    expires: float
    state: str = "name"
    name: str = ""
    person_id: str = ""
    sample_count: int = 0
    busy: bool = False


class SpeakerDialogue:
    def __init__(self, create_person, store_audio, clock=time.monotonic):
        self.sessions = {}
        self.create_person = create_person
        self.store_audio = store_audio
        self.clock = clock

    def prune(self):
        for key, session in list(self.sessions.items()):
            if session.expires <= self.clock():
                self.sessions.pop(key, None)

    def pending(self, owner_id, device_id):
        self.prune()
        session = self.sessions.get(device_id)
        if session is None or session.owner_id != owner_id:
            return None
        return {"session_id": session.session_id, "display_name": session.name,
                "state": session.state, "sample_count": session.sample_count}

    def approve(self, owner_id, device_id, session_id):
        self.prune()
        session = self.sessions.get(device_id)
        if (session is None or session.owner_id != owner_id
                or session.session_id != session_id or session.state != "approval"):
            raise ValueError("录入请求不存在、已过期或尚未获得本人同意")
        session.state = "approved"

    def cancel(self, owner_id, device_id, session_id):
        session = self.sessions.get(device_id)
        if session and session.owner_id == owner_id and session.session_id == session_id:
            self.sessions.pop(device_id, None)

    def disconnect(self, device_id):
        self.sessions.pop(device_id, None)

    async def handle(self, owner_id, device_id, text, audio):
        self.prune()
        text = clean(text)
        session = self.sessions.get(device_id)
        if session and session.owner_id != owner_id:
            self.sessions.pop(device_id, None)
            session = None
        if session is None:
            if text not in {"记住我的声音", "echo记住我的声音", "请记住我的声音"}:
                return None
            if len(self.sessions) >= 64:
                return "现在录入请求较多，请稍后再试。"
            session = EnrollmentSession(uuid.uuid4().hex, owner_id, device_id, self.clock()+600)
            self.sessions[device_id] = session
            return "可以，你希望我怎么称呼你？"
        if text in {"取消", "取消录入", "停止录入", "不同意", "我不同意"}:
            self.sessions.pop(device_id, None)
            return "已停止录入。已保存的片段可以在 App 的人员声纹中删除。"
        if session.busy:
            return "正在处理上一段，请稍等。"
        if session.state == "name":
            name = re.sub(r"^(请叫我|叫我|我是|我叫)", "", text).strip()
            if not name or len(name) > 20:
                return "请告诉我一个简短的称呼，比如叫我叶子。"
            session.name = name
            session.state = "consent"
            return f"好的，{name}。我会保存声纹用于称呼识别，原始录音处理后不保留，可随时删除。你同意吗？"
        if session.state == "consent":
            if text not in {"同意", "我同意", "同意录入"}:
                return "请明确说我同意，或者取消录入。"
            session.state = "approval"
            return "请设备管理员在 App 的人员声纹中确认这次录入，确认后对我说开始录入。"
        if session.state == "approval":
            return "还在等待设备管理员确认，请在 App 的人员声纹中批准这次录入。"
        if session.state == "approved":
            if text not in {"开始录入", "开始", "继续录入"}:
                return "准备好后请说开始录入。"
            session.busy = True
            try:
                person_id = await self.create_person(owner_id, device_id, session.name)
                self.prune()
                if self.sessions.get(device_id) is not session:
                    return "录入已取消，请在 App 检查并删除未完成的档案。"
                session.person_id = person_id
                session.state = "collecting"
                return "请用平常的声音读这句话，至少三秒。" + PROMPTS[0]
            finally:
                session.busy = False
        session.busy = True
        try:
            result = await self.store_audio(owner_id, device_id, session.person_id, audio)
            self.prune()
            if self.sessions.get(device_id) is not session:
                return "录入已取消，已处理的片段可在 App 删除。"
            session.sample_count = result["sample_count"]
            if result["status"] == "active":
                self.sessions.pop(device_id, None)
                return f"录入和验证完成了，{session.name}。"
            if session.sample_count == 3:
                return "三段已保存。最后请读一句新话进行独立验证。" + PROMPTS[3]
            return "这段已保存，接下来请读。" + PROMPTS[session.sample_count]
        finally:
            session.busy = False
