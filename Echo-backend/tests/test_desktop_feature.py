# ruff: noqa: ARG002

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.desktop.application.desktop_service import DesktopService
from features.desktop.application.manage_nodes import DesktopNodeManagement
from features.desktop.application.node_hub import DesktopNodeHub
from features.desktop.domain.entities import (
    DesktopActionError,
    DesktopNode,
    DesktopOfflineError,
    DesktopPairingError,
    DesktopTimeoutError,
)
from features.desktop.domain.rules import (
    normalize_capabilities,
    normalize_pairing_code,
    pairing_code_hash,
    validate_action_arguments,
)


class FakeChannel:
    def __init__(self, node: DesktopNode):
        self.node_id = node.node_id
        self.user_id = node.user_id
        self.capabilities = node.capabilities
        self.sent: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.sent.append(payload)


class FakeRepository:
    def __init__(self):
        self.pairing: dict[str, tuple[str, datetime]] = {}
        self.node: DesktopNode | None = None
        self.actions: list[tuple[str, str, str | None]] = []

    def create_pairing_code(self, *, code_hash, user_id, expires_at):
        if code_hash in self.pairing:
            return False
        self.pairing[code_hash] = (user_id, expires_at)
        return True

    def pair_node(
        self,
        *,
        code_hash,
        node_name,
        fingerprint,
        token_hash,
        node_id,
        capabilities,
        now,
    ):
        pair = self.pairing.get(code_hash)
        if pair is None or pair[1] <= now:
            return None
        self.pairing.pop(code_hash)
        self.node = DesktopNode(
            node_id=node_id,
            user_id=pair[0],
            name=node_name,
            capabilities=capabilities,
            status="offline",
        )
        return self.node

    def find_node_by_token_hash(self, token_hash):
        return None

    def list_nodes(self, user_id):
        return [self.node] if self.node else []

    def revoke_node(self, user_id, node_id):
        return False

    def mark_online(self, node_id, capabilities):
        return None

    def mark_offline(self, node_id):
        return None

    def record_action_start(self, **kwargs):
        self.actions.append((kwargs["action"], "running", None))

    def record_action_finish(self, **kwargs):
        self.actions.append(("", kwargs["status"], kwargs["error_code"]))


class DesktopDomainTests(unittest.TestCase):
    def test_pairing_code_and_arguments_are_normalized(self):
        self.assertEqual(normalize_pairing_code(" 12 34 56 "), "123456")
        self.assertEqual(
            normalize_capabilities(["open_app", "open_app", "unknown"]),
            ("open_app",),
        )
        self.assertEqual(
            validate_action_arguments("open_app", {"app": "notepad"}),
            {"app": "notepad"},
        )
        with self.assertRaises(ValueError):
            validate_action_arguments("open_app", {"app": "cmd"})

    def test_pairing_code_hash_is_stable_and_secret_bound(self):
        self.assertEqual(
            pairing_code_hash("123456", "secret-a"),
            pairing_code_hash("123456", "secret-a"),
        )
        self.assertNotEqual(
            pairing_code_hash("123456", "secret-a"),
            pairing_code_hash("123456", "secret-b"),
        )


class DesktopManagementTests(unittest.TestCase):
    def test_pairing_consumes_code_once(self):
        repository = FakeRepository()
        management = DesktopNodeManagement(repository, "secret", 600)
        pairing = management.create_pairing_code("user-1")
        paired = management.pair_node(
            code=pairing.code,
            node_name="我的电脑",
            fingerprint="fp",
            capabilities=("open_app",),
        )
        self.assertEqual(paired.node.user_id, "user-1")
        self.assertTrue(paired.token)
        with self.assertRaises(DesktopPairingError):
            management.pair_node(
                code=pairing.code,
                node_name="再来一次",
                fingerprint="fp",
                capabilities=(),
            )


class DesktopHubTests(unittest.TestCase):
    def _node(self) -> DesktopNode:
        return DesktopNode(
            node_id="dnode_test",
            user_id="user-1",
            name="测试电脑",
            capabilities=("open_app",),
        )

    def test_execute_routes_result_to_waiting_command(self):
        async def scenario():
            node = self._node()
            channel = FakeChannel(node)
            hub = DesktopNodeHub()
            hub.register(node, channel)
            task = asyncio.create_task(
                hub.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                    timeout_seconds=2,
                )
            )
            await asyncio.sleep(0)
            command = channel.sent[0]
            hub.handle_message(
                node,
                {
                    "type": "result",
                    "command_id": command["command_id"],
                    "ok": True,
                    "data": {"pid": 1},
                },
            )
            result = await task
            self.assertEqual(result.data["pid"], 1)

        asyncio.run(scenario())

    def test_execute_raises_offline_without_node(self):
        async def scenario():
            hub = DesktopNodeHub()
            with self.assertRaises(DesktopOfflineError):
                await hub.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                    timeout_seconds=1,
                )

        asyncio.run(scenario())

    def test_execute_times_out(self):
        async def scenario():
            node = self._node()
            hub = DesktopNodeHub()
            hub.register(node, FakeChannel(node))
            with self.assertRaises(DesktopTimeoutError):
                await hub.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                    timeout_seconds=0.05,
                )

        asyncio.run(scenario())

    def test_execute_raises_denied_error(self):
        async def scenario():
            node = self._node()
            channel = FakeChannel(node)
            hub = DesktopNodeHub()
            hub.register(node, channel)
            task = asyncio.create_task(
                hub.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                    timeout_seconds=2,
                )
            )
            await asyncio.sleep(0)
            command = channel.sent[0]
            hub.handle_message(
                node,
                {
                    "type": "result",
                    "command_id": command["command_id"],
                    "ok": False,
                    "error": {"code": "user_denied", "message": "no"},
                },
            )
            with self.assertRaises(DesktopActionError) as caught:
                await task
            self.assertEqual(caught.exception.code, "user_denied")

        asyncio.run(scenario())


class DesktopServiceTests(unittest.TestCase):
    def test_service_records_completed_action(self):
        async def scenario():
            node = DesktopNode(
                node_id="dnode_test",
                user_id="user-1",
                name="测试电脑",
                capabilities=("open_app",),
            )
            channel = FakeChannel(node)
            hub = DesktopNodeHub()
            hub.register(node, channel)
            repository = FakeRepository()
            management = DesktopNodeManagement(repository, "secret", 600)
            service = DesktopService(repository, hub, management, 5)
            task = asyncio.create_task(
                service.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                )
            )
            await asyncio.sleep(0)
            command = channel.sent[0]
            hub.handle_message(
                node,
                {
                    "type": "result",
                    "command_id": command["command_id"],
                    "ok": True,
                    "data": {},
                },
            )
            await task
            self.assertEqual(repository.actions[0][1], "running")
            self.assertEqual(repository.actions[-1][1], "completed")

        asyncio.run(scenario())

    def test_service_catches_hub_timeout(self):
        async def scenario():
            node = DesktopNode(
                node_id="dnode_test",
                user_id="user-1",
                name="测试电脑",
            )
            hub = DesktopNodeHub()
            hub.register(node, FakeChannel(node))
            repository = FakeRepository()
            management = DesktopNodeManagement(repository, "secret", 600)
            service = DesktopService(repository, hub, management, 0.05)
            with self.assertRaises(DesktopTimeoutError):
                await service.execute(
                    user_id="user-1",
                    action="open_app",
                    arguments={"app": "notepad"},
                    timeout_seconds=0.05,
                )
            self.assertEqual(repository.actions[-1][1], "timed_out")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
