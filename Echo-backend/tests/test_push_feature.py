import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.push.application.manage_targets import ManagePushTargets
from features.push.infrastructure.getui_sender import GetuiNotificationSender
from features.push.infrastructure.postgres_repository import (
    NotificationOutboxItem,
    PushTarget,
)


class FakePushRepository:
    def __init__(self, *, targets=None):
        self.item = NotificationOutboxItem(
            notification_id="notification-1",
            user_id="user-1",
            title="Echo",
            body_policy="hidden",
            body="private message",
            payload={
                "schema_version": "1",
                "type": "proactive_chat",
                "route": "chat",
                "notification_id": "notification-1",
            },
            attempt_count=1,
        )
        self.targets = targets or (PushTarget("device-1", "cid-1"),)
        self.sent = None
        self.retried = None
        self.discarded = None
        self.invalidated = []

    def claim_due(self):
        item, self.item = self.item, None
        return item

    def list_targets(self, _user_id):
        return self.targets

    def mark_sent(self, notification_id, device_ids):
        self.sent = (notification_id, device_ids)

    def mark_retry(self, item, error_code):
        self.retried = (item.notification_id, error_code)

    def mark_discarded(self, notification_id, error_code):
        self.discarded = (notification_id, error_code)

    def invalidate_target(self, device_id):
        self.invalidated.append(device_id)


class FakePushTargetWriter:
    def __init__(self):
        self.registered = None
        self.revoked = None

    def register_target(self, **kwargs):
        self.registered = kwargs

    def revoke_target(self, **kwargs):
        self.revoked = kwargs


class ManagePushTargetsTests(unittest.TestCase):
    def test_registers_and_revokes_through_repository_port(self):
        repository = FakePushTargetWriter()
        manager = ManagePushTargets(repository)

        manager.register(
            user_id="user-1",
            device_id="device-1",
            platform="android",
            provider="getui",
            token="cid-1",
            app_version="1.0.7",
            environment="production",
            locale="zh-CN",
        )
        manager.unregister(user_id="user-1", device_id="device-1")

        self.assertEqual(repository.registered["token"], "cid-1")
        self.assertEqual(
            repository.revoked,
            {"user_id": "user-1", "device_id": "device-1"},
        )


class FakeAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, path, **kwargs):
        self.requests.append((path, kwargs))
        status_code, payload = self.responses.pop(0)
        return httpx.Response(
            status_code,
            json=payload,
            request=httpx.Request("POST", f"https://getui.test{path}"),
        )


class GetuiNotificationSenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticates_and_sends_hidden_notification_to_cid(self):
        repository = FakePushRepository()
        client = FakeAsyncClient(
            [
                (200, {"code": 0, "data": {"token": "token-1", "expire_time": 2_000_000}}),
                (200, {"code": 0, "data": {"cid-1": "successed_online"}}),
            ]
        )
        sender = GetuiNotificationSender(
            repository=repository,
            app_id="app-id",
            app_key="app-key",
            master_secret="master-secret",
        )

        with (
            patch(
                "features.push.infrastructure.getui_sender.httpx.AsyncClient",
                return_value=client,
            ),
            patch("features.push.infrastructure.getui_sender.time.time", return_value=1000),
        ):
            self.assertTrue(await sender.run_once())

        auth_path, auth_request = client.requests[0]
        self.assertEqual(auth_path, "/auth")
        expected_sign = hashlib.sha256(b"app-key1000000master-secret").hexdigest()
        self.assertEqual(auth_request["json"]["sign"], expected_sign)

        push_path, push_request = client.requests[1]
        self.assertEqual(push_path, "/push/single/cid")
        self.assertEqual(push_request["headers"], {"token": "token-1"})
        body = push_request["json"]
        self.assertEqual(body["audience"], {"cid": ["cid-1"]})
        notification = body["push_message"]["notification"]
        self.assertEqual(notification["body"], "Echo 发来了一条消息")
        self.assertEqual(notification["click_type"], "payload")
        self.assertEqual(json.loads(notification["payload"])["route"], "chat")
        self.assertEqual(repository.sent, ("notification-1", ("device-1",)))

    async def test_invalid_cid_is_deactivated_and_outbox_is_discarded(self):
        repository = FakePushRepository()
        client = FakeAsyncClient(
            [
                (200, {"code": 0, "data": {"token": "token-1", "expire_time": 2_000_000}}),
                (200, {"code": 20001, "msg": "target user is invalid"}),
            ]
        )
        sender = GetuiNotificationSender(
            repository=repository,
            app_id="app-id",
            app_key="app-key",
            master_secret="master-secret",
        )

        with (
            patch(
                "features.push.infrastructure.getui_sender.httpx.AsyncClient",
                return_value=client,
            ),
            patch("features.push.infrastructure.getui_sender.time.time", return_value=1000),
        ):
            await sender.run_once()

        self.assertEqual(repository.invalidated, ["device-1"])
        self.assertEqual(
            repository.discarded,
            ("notification-1", "all_targets_invalid"),
        )

    async def test_harmony_target_uses_harmony_credentials(self):
        repository = FakePushRepository(
            targets=(PushTarget("device-harmony", "cid-harmony", "harmonyos"),)
        )
        client = FakeAsyncClient(
            [
                (200, {"code": 0, "data": {"token": "harmony-token", "expire_time": 2_000_000}}),
                (200, {"code": 0, "data": {"cid-harmony": "successed_online"}}),
            ]
        )
        sender = GetuiNotificationSender(
            repository=repository,
            app_id="android-app-id",
            app_key="android-app-key",
            master_secret="android-master-secret",
            harmony_app_id="harmony-app-id",
            harmony_app_key="harmony-app-key",
            harmony_master_secret="harmony-master-secret",
        )

        with (
            patch(
                "features.push.infrastructure.getui_sender.httpx.AsyncClient",
                return_value=client,
            ),
            patch("features.push.infrastructure.getui_sender.time.time", return_value=1000),
        ):
            self.assertTrue(await sender.run_once())

        auth_path, auth_request = client.requests[0]
        self.assertEqual(auth_path, "/auth")
        expected_sign = hashlib.sha256(
            b"harmony-app-key1000000harmony-master-secret"
        ).hexdigest()
        self.assertEqual(auth_request["json"]["sign"], expected_sign)
        self.assertEqual(repository.sent, ("notification-1", ("device-harmony",)))

    async def test_missing_credentials_uses_existing_retry_policy(self):
        repository = FakePushRepository()
        sender = GetuiNotificationSender(
            repository=repository,
            app_id="",
            app_key="",
            master_secret="",
        )

        self.assertTrue(await sender.run_once())
        self.assertEqual(
            repository.retried,
            ("notification-1", "getui_credentials_unavailable"),
        )


if __name__ == "__main__":
    unittest.main()
