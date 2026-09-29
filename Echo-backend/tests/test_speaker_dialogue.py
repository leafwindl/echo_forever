import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from features.devices.application.speaker_dialogue import SpeakerDialogue


class SpeakerDialogueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 0
        self.create = AsyncMock(return_value="person")
        self.store = AsyncMock()
        self.flow = SpeakerDialogue(self.create, self.store, clock=lambda: self.now)

    async def say(self, text):
        return await self.flow.handle("owner", "device", text, b"audio")

    async def request(self):
        await self.say("记住我的声音")
        await self.say("叫我叶子")
        await self.say("我同意")
        return self.flow.pending("owner", "device")["session_id"]

    async def test_normal_chat_does_not_enroll(self):
        self.assertIsNone(await self.say("今天天气怎么样"))
        self.create.assert_not_awaited()
        self.store.assert_not_awaited()

    async def test_requires_explicit_consent_and_owner_approval(self):
        await self.say("记住我的声音")
        await self.say("叫我叶子")
        await self.say("好的")
        session = self.flow.pending("owner", "device")
        self.assertEqual(session["state"], "consent")
        with self.assertRaises(ValueError):
            self.flow.approve("owner", "device", session["session_id"])
        await self.say("我同意")
        await self.say("开始录入")
        self.create.assert_not_awaited()
        self.store.assert_not_awaited()
        with self.assertRaises(ValueError):
            self.flow.approve("other", "device", session["session_id"])
        self.assertIsNone(self.flow.pending("other", "device"))

    async def test_three_samples_and_independent_verification(self):
        session_id = await self.request()
        self.flow.approve("owner", "device", session_id)
        await self.say("开始录入")
        self.create.assert_awaited_once_with("owner", "device", "叶子")
        self.store.assert_not_awaited()
        for count, state in [(1, "collecting"), (2, "collecting"), (3, "verifying"), (3, "active")]:
            self.store.return_value = {"sample_count": count, "status": state}
            reply = await self.say("这是新的一段录音")
        self.assertIn("验证完成", reply)
        self.assertIsNone(self.flow.pending("owner", "device"))
        self.assertEqual(self.store.await_count, 4)

    async def test_cancel_expire_and_disconnect_do_not_resume(self):
        for action in ("cancel", "expire", "disconnect"):
            session_id = await self.request()
            self.flow.approve("owner", "device", session_id)
            if action == "cancel":
                await self.say("取消")
            elif action == "expire":
                self.now += 601
            else:
                self.flow.disconnect("device")
            self.assertIsNone(await self.say("开始录入"))
        self.create.assert_not_awaited()

    async def test_failed_sample_can_retry(self):
        session_id = await self.request()
        self.flow.approve("owner", "device", session_id)
        await self.say("开始录入")
        self.store.side_effect = ValueError("too quiet")
        with self.assertRaises(ValueError):
            await self.say("样本")
        self.assertFalse(self.flow.sessions["device"].busy)
        self.assertEqual(self.flow.sessions["device"].sample_count, 0)

    async def test_overlapping_turn_does_not_add_another_sample(self):
        session_id = await self.request()
        self.flow.approve("owner", "device", session_id)
        await self.say("开始录入")
        gate = asyncio.Event()

        async def wait(*args):
            await gate.wait()
            return {"sample_count": 1, "status": "collecting"}

        self.store.side_effect = wait
        task = asyncio.create_task(self.say("样本"))
        await asyncio.sleep(0)
        self.assertIn("正在处理", await self.say("又一个样本"))
        gate.set()
        await task
        self.store.assert_awaited_once()
