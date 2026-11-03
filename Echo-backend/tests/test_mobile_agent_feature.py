from __future__ import annotations

import asyncio
import unittest

from features.mobile_agent.application.hub import MobileAgentHub
from features.mobile_agent.application.management import MobileAgentManagement
from features.mobile_agent.domain.entities import (
    MobileAgentDevice,
    MobileAgentOfflineError,
    MobileAgentPairingError,
)


class FakeRepository:
    def __init__(self):
        self.codes: dict[str, dict] = {}
        self.devices: dict[str, MobileAgentDevice] = {}
        self.online: set[str] = set()

    def create_pairing_code(self, *, code_hash, user_id, expires_at):
        self.codes[code_hash] = {
            "user_id": user_id,
            "expires_at": expires_at,
            "consumed": False,
        }
        return True

    def pair_device(self, *, code_hash, device_name, token_hash, device_id, now):
        code = self.codes.get(code_hash)
        if code is None or code["consumed"] or code["expires_at"] <= now:
            return None
        code["consumed"] = True
        device = MobileAgentDevice(
            device_id=device_id,
            user_id=code["user_id"],
            name=device_name,
            status="offline",
        )
        self.devices[token_hash] = device
        return device

    def find_by_token_hash(self, token_hash):
        return self.devices.get(token_hash)

    def list_devices(self, user_id):
        return [d for d in self.devices.values() if d.user_id == user_id]

    def revoke_device(self, user_id, device_id):
        for token_hash, device in list(self.devices.items()):
            if device.user_id == user_id and device.device_id == device_id:
                self.devices.pop(token_hash)
                return True
        return False

    def mark_online(self, device_id):
        self.online.add(device_id)

    def mark_offline(self, device_id):
        self.online.discard(device_id)


class MobileAgentManagementTests(unittest.TestCase):
    def test_pairing_code_and_token_are_hashed(self):
        repository = FakeRepository()
        management = MobileAgentManagement(
            repository=repository,
            pairing_secret="test-secret",
            pairing_code_ttl_seconds=300,
        )
        code = management.create_pairing_code("user-1")
        self.assertNotIn(code.code, repository.codes)
        paired = management.pair_device(code=code.code, device_name="手机")
        self.assertEqual(paired.device.user_id, "user-1")
        self.assertNotEqual(paired.token, "")
        self.assertIsNotNone(management.authenticate(paired.token))
        self.assertIsNone(management.authenticate("wrong-token"))

    def test_invalid_pairing_code_is_rejected(self):
        management = MobileAgentManagement(
            repository=FakeRepository(),
            pairing_secret="test-secret",
            pairing_code_ttl_seconds=300,
        )
        with self.assertRaises(MobileAgentPairingError):
            management.pair_device(code="NOTACODE", device_name="手机")


class FakeChannel:
    def __init__(self, device, result):
        self.device_id = device.device_id
        self.user_id = device.user_id
        self.sent = []
        self.result = result

    async def send(self, payload):
        self.sent.append(payload)
        if payload.get("type") == "command":
            asyncio.get_running_loop().call_soon(
                lambda: self.result(payload)
            )

    async def close(self):
        pass


class MobileAgentHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_round_trip(self):
        device = MobileAgentDevice(
            device_id="mdev_test",
            user_id="user-1",
            name="手机",
        )
        hub = MobileAgentHub()
        channel = FakeChannel(
            device,
            lambda payload: hub.handle_message(
                device,
                {
                    "type": "result",
                    "command_id": payload["command_id"],
                    "data": {"kind": "home"},
                },
            ),
        )
        hub.register(device, channel)
        result = await hub.execute(
            user_id="user-1",
            device_id="mdev_test",
            action="action",
            arguments={"kind": "home"},
            timeout_seconds=2,
        )
        self.assertEqual(result.data, {"kind": "home"})
        self.assertEqual(channel.sent[0]["type"], "command")

    async def test_offline_device_is_rejected(self):
        hub = MobileAgentHub()
        with self.assertRaises(MobileAgentOfflineError):
            await hub.execute(
                user_id="user-1",
                device_id="missing",
                action="observe",
                arguments={},
                timeout_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
