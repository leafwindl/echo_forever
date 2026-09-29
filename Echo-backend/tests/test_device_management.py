import math
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.devices.infrastructure.device_management import (
    create_provisioning_session,
    hash_credential,
    normalize_client_id,
    normalize_device_id,
)
from features.devices.infrastructure.speaker_verification import (
    cosine_similarity,
    extract_speaker_embedding,
)
from features.devices.interface import router as device_router
from features.devices.interface.schemas import DevicePairingClaimRequest
from shared.interface.dependencies import CurrentUser


class DeviceManagementTests(unittest.TestCase):
    def test_normalizes_device_identifiers_and_hashes_credentials(self):
        self.assertEqual(normalize_device_id(" AA:BB "), "aa:bb")
        self.assertEqual(normalize_client_id(" Client-1 "), "client-1")
        self.assertEqual(hash_credential("secret"), hash_credential("secret"))
        self.assertNotEqual(hash_credential("secret"), hash_credential("other"))

    def test_speaker_embedding_is_stable_and_comparable(self):
        pcm = b"".join(
            struct.pack("<h", int(7000 * math.sin(2 * math.pi * 220 * index / 16000)))
            for index in range(16000 * 3)
        )
        embedding = extract_speaker_embedding(pcm)
        self.assertTrue(embedding)
        self.assertAlmostEqual(cosine_similarity(embedding, embedding), 1.0, places=5)
        self.assertEqual(extract_speaker_embedding(b"\x00" * 100), [])

    def test_claim_pairing_allows_code_only_claims(self):
        expected = {
            "device_id": "aa:bb",
            "client_id": "client-1",
            "credential": "edc_test",
        }
        with patch.object(device_router, "claim_pairing", return_value=expected) as claim:
            result = device_router.claim_device_pairing(
                DevicePairingClaimRequest(code="123456"),
                CurrentUser(user_id="user-1"),
            )
        self.assertEqual(result, expected)
        claim.assert_called_once_with(user_id="user-1", pairing_id="", code="123456")

    def test_create_provisioning_session_uses_current_user(self):
        expected = {"claim_token": "ep_test", "expires_in": 600}
        with patch.object(
            device_router, "create_provisioning_session", return_value=expected
        ) as create_session:
            result = device_router.create_device_provisioning_session(CurrentUser(user_id="user-1"))
        self.assertEqual(result, expected)
        create_session.assert_called_once_with(user_id="user-1")

    def test_provisioning_session_tokens_are_hashed(self):
        with patch("features.devices.infrastructure.device_management.transaction") as transaction:
            cursor = transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            result = create_provisioning_session(user_id="user-1")

        self.assertTrue(result["claim_token"].startswith("ep_"))
        self.assertEqual(result["expires_in"], 600)
        params = cursor.execute.call_args.args[1]
        self.assertEqual(params[1], "user-1")
        self.assertNotEqual(params[2], result["claim_token"])
        self.assertEqual(params[2], hash_credential(result["claim_token"]))

    def test_bootstrap_claims_direct_provisioning_token(self):
        expected = {
            "device_id": "aa:bb",
            "client_id": "client-1",
            "credential": "edc_direct",
        }
        with (
            patch.object(device_router, "validate_device_credential", return_value=None),
            patch.object(device_router, "_resolve_device_user", return_value=None),
            patch.object(
                device_router, "claim_provisioning_session", return_value=expected
            ) as claim,
            patch.object(device_router, "create_pairing") as create_pairing,
            patch.object(device_router, "touch_device", return_value=None) as touch,
        ):
            import asyncio

            result = asyncio.run(
                device_router.device_bootstrap(
                    device_id="aa:bb",
                    client_id="client-1",
                    authorization=None,
                    echo_bind_token="ep_test",
                    firmware_version="0.1.4",
                )
            )
        self.assertIsNone(result.activation)
        self.assertEqual(result.websocket.token, "edc_direct")
        create_pairing.assert_not_called()
        claim.assert_called_once_with(
            claim_token="ep_test",
            device_id="aa:bb",
            client_id="client-1",
            firmware_version="0.1.4",
        )
        touch.assert_called_once_with(
            device_id="aa:bb",
            client_id="client-1",
            firmware_version="0.1.4",
        )

    def test_bootstrap_binds_legacy_device_to_configured_user(self):
        expected = {
            "device_id": "aa:bb",
            "client_id": "client-1",
            "credential": "edc_legacy",
        }
        with (
            patch.object(device_router, "validate_device_credential", return_value=None),
            patch.object(device_router, "_resolve_device_user", return_value="user-legacy"),
            patch.object(device_router, "bind_legacy_device", return_value=expected) as bind,
            patch.object(device_router, "create_pairing") as create_pairing,
            patch.object(device_router, "touch_device", return_value=None),
        ):
            import asyncio

            result = asyncio.run(
                device_router.device_bootstrap(
                    device_id="aa:bb",
                    client_id="client-1",
                    authorization=None,
                    echo_bind_token=None,
                )
            )
        self.assertIsNone(result.activation)
        self.assertEqual(result.websocket.token, "edc_legacy")
        create_pairing.assert_not_called()
        bind.assert_called_once_with(
            user_id="user-legacy",
            device_id="aa:bb",
            client_id="client-1",
            firmware_version=device_router.settings.echo_firmware_version,
        )

    def test_bootstrap_returns_pairing_only_activation_for_unknown_device(self):
        with (
            patch.object(device_router, "validate_device_credential", return_value=None),
            patch.object(device_router, "_resolve_device_user", return_value=None),
            patch.object(
                device_router,
                "create_pairing",
                return_value={"pairing_id": "pair-1", "code": "123456"},
            ),
            patch.object(
                device_router, "ensure_bootstrap_credential", return_value="edc_bootstrap"
            ),
            patch.object(device_router, "touch_device", return_value=None),
        ):
            import asyncio

            result = asyncio.run(
                device_router.device_bootstrap(
                    device_id="aa:bb",
                    client_id="client-1",
                    authorization=None,
                    echo_bind_token=None,
                )
            )
        self.assertIsNotNone(result.activation)
        self.assertTrue(result.activation.pairing_only)
        self.assertEqual(result.activation.code, "123456")
        self.assertEqual(result.websocket.token, "edc_bootstrap")


if __name__ == "__main__":
    unittest.main()
