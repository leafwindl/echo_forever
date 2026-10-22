"""Opt-in real PostgreSQL tests. Run via scripts/run_device_lab.py --test."""
import os
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db.postgres_connection import get_connection, transaction
from features.devices.interface import speaker_router as routes
from features.devices.interface import router as device_routes
from features.devices.infrastructure import speaker_people_repository as repository
from features.devices.infrastructure.speaker_people_container import people_service
from features.devices.domain.speaker_people import SpeakerPeopleError
from features.devices.domain.speaker_vectors import SpeakerUnavailable
from features.devices.infrastructure.device_management import rotate_device_credential
from shared.interface.dependencies import CurrentUser, get_current_user


@unittest.skipUnless(os.environ.get("ECHO_LAB_DB_TEST") == "1", "isolated lab DB only")
class SpeakerLabTests(unittest.TestCase):
    def setUp(self):
        with get_connection() as conn:
            if (conn.info.dbname != "echo_device_lab" or conn.info.host != "127.0.0.1"
                    or conn.info.port != 15432):
                raise RuntimeError("Refusing to modify a non-lab database")
        self.device = "lab-test-" + uuid.uuid4().hex
        self.owner = "lab-owner-" + uuid.uuid4().hex
        with transaction() as conn:
            conn.execute("INSERT INTO devices (device_id,owner_user_id) VALUES (%s,%s)",
                         (self.device, self.owner))
        app = FastAPI()
        app.include_router(routes.router)
        app.include_router(device_routes.router)
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(self.owner)
        self.client = TestClient(app)
        self.client.__enter__()
        self.base = f"/devices/{self.device}/speakers"

    def tearDown(self):
        self.client.__exit__(None, None, None)
        with transaction() as conn:
            conn.execute("DELETE FROM speaker_people WHERE device_id=%s", (self.device,))
            conn.execute("DELETE FROM device_credentials WHERE device_id=%s", (self.device,))
            conn.execute("DELETE FROM devices WHERE device_id=%s", (self.device,))

    def create(self, name="叶子"):
        response = self.client.post(self.base, json={"display_name": name, "consent": True})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["person_id"]

    def sample(self, person, index, vector=None):
        with patch.object(people_service, "extract", return_value=(vector or [1., 0.], "campp-zh:test")):
            return self.client.post(f"{self.base}/{person}/samples",
                                    files={"audio": ("test.pcm", bytes([index]) * 96000)})

    def test_four_unique_samples_activate_then_delete(self):
        person = self.create()
        for index, status in [(1, "collecting"), (2, "collecting"), (3, "verifying"), (4, "active")]:
            response = self.sample(person, index)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], status)
        self.assertEqual(self.sample(person, 5).status_code, 409)
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM speaker_people WHERE person_id=%s", (person,)).fetchone()
        self.assertEqual(len(row["samples"]), 3)
        self.assertEqual(len(row["sample_hashes"]), 4)
        self.assertEqual(self.client.delete(f"{self.base}/{person}").status_code, 204)
        self.assertEqual(self.client.get(self.base).json()["items"], [])

    def test_duplicate_audio_and_different_speaker_rejected(self):
        person = self.create()
        self.assertEqual(self.sample(person, 1).status_code, 200)
        self.assertEqual(self.sample(person, 1).status_code, 409)
        self.assertEqual(self.sample(person, 2, [0., 1.]).status_code, 422)
        self.assertEqual(self.client.get(self.base).json()["items"][0]["sample_count"], 1)

    def test_duplicate_person_fails_independent_verification(self):
        first, second = self.create(), self.create("朋友")
        for index in range(1, 5):
            self.assertEqual(self.sample(first, index).status_code, 200)
        for index in range(1, 4):
            self.assertEqual(self.sample(second, index).status_code, 200)
        self.assertEqual(self.sample(second, 4).status_code, 422)

    def test_owner_change_during_inference_prevents_save(self):
        person = self.create()
        row = repository.load_person(self.owner, self.device, person)
        with transaction() as conn:
            conn.execute("UPDATE devices SET owner_user_id=%s WHERE device_id=%s",
                         ("another-owner", self.device))
        with self.assertRaises(SpeakerPeopleError) as error:
            repository.save_sample(self.owner, self.device, person, [1., 0.],
                               "campp-zh:test", row["updated_at"], "hash")
        self.assertEqual(error.exception.code, "not_found")

    def test_explicit_consent_and_service_failure(self):
        response = self.client.post(self.base, json={"display_name": "叶子", "consent": False})
        self.assertEqual(response.status_code, 422)
        person = self.create()
        with patch.object(people_service, "extract", side_effect=SpeakerUnavailable("unavailable")):
            response = self.client.post(f"{self.base}/{person}/samples",
                                       files={"audio": ("test.pcm", b"\0" * 96000)})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.base).json()["items"][0]["sample_count"], 0)

    def test_hardware_calibration_verification_fallback_and_cascade(self):
        person = self.create()
        for index in range(1, 5):
            self.assertEqual(self.sample(person, index).status_code, 200)
        path = f"{self.base}/{person}/calibration"
        with patch.dict(device_routes._active_device_sessions, {self.device: object()}):
            self.assertEqual(self.client.post(path, json={"consent": False}).status_code, 422)
            started = self.client.post(path, json={"consent": True})
        self.assertEqual(started.status_code, 200, started.text)
        session = people_service.calibration
        with patch.object(people_service, "extract", return_value=([0., 1.], "campp-zh:test")):
            for index in range(5, 8):
                self.assertIn("已保存", session.consume(self.owner, self.device, bytes([index]), people_service.extract))
            self.assertIn("未通过", session.consume(
                self.owner, self.device, b"bad", lambda _: ([1., 0.], "campp-zh:test"),
            ))
            self.assertIn("独立验证", session.consume(self.owner, self.device, b"verify", people_service.extract))
            self.assertTrue(self.client.get(self.base).json()["items"][0]["hardware_calibrated"])
            self.assertEqual(people_service.recognize(self.device, b"voice")["speaker_role"], "known")
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertFalse(self.client.get(self.base).json()["items"][0]["hardware_calibrated"])
        with patch.object(people_service, "extract", return_value=([0., 1.], "campp-zh:test")):
            self.assertEqual(people_service.recognize(self.device, b"voice")["speaker_role"], "unknown")
        with patch.object(people_service, "extract", return_value=([1., 0.], "campp-zh:test")):
            self.assertEqual(people_service.recognize(self.device, b"voice")["speaker_role"], "known")
        with patch.dict(device_routes._active_device_sessions, {self.device: object()}):
            self.assertEqual(self.client.post(path, json={"consent": True}).status_code, 200)
        session.cancel(self.owner, self.device)
        self.assertIsNone(self.client.get(f"/devices/{self.device}/speaker-calibration").json()["session"])
        self.assertEqual(self.client.delete(f"{self.base}/{person}").status_code, 204)
        with get_connection() as conn:
            count = conn.execute(
                "SELECT count(*) FROM speaker_device_calibrations WHERE person_id=%s", (person,),
            ).fetchone()["count"]
        self.assertEqual(count, 0)

    def test_hardware_calibration_rejects_other_member_and_cross_account(self):
        first = self.create()
        second = self.create("朋友")
        for person in (first, second):
            for index in range(1, 5):
                vector = [0., 1.] if person == second else [1., 0.]
                self.assertEqual(self.sample(person, index, vector).status_code, 200)
        with patch.dict(device_routes._active_device_sessions, {self.device: object()}):
            self.assertEqual(self.client.post(
                f"{self.base}/{second}/calibration", json={"consent": True},
            ).status_code, 200)
        session = people_service.calibration
        for index in range(5, 8):
            session.consume(self.owner, self.device, bytes([index]),
                            lambda _: ([1., 0.], "campp-zh:test"))
        self.assertIn("未通过", session.consume(
            self.owner, self.device, b"verify", lambda _: ([1., 0.], "campp-zh:test"),
        ))
        self.assertFalse(self.client.get(self.base).json()["items"][1]["hardware_calibrated"])
        self.assertIsNone(session.pending("other", self.device))
        self.client.app.dependency_overrides[get_current_user] = (
            lambda: CurrentUser("other-owner")
        )
        self.assertEqual(self.client.delete(f"{self.base}/{first}/calibration").status_code, 404)
        self.client.app.dependency_overrides[get_current_user] = (
            lambda: CurrentUser(self.owner)
        )
        session.cancel(self.owner, self.device)

    def test_http_probe_needs_authenticated_websocket_reply(self):
        path = f"/devices/{self.device}/probe"
        self.assertEqual(self.client.post(path).status_code, 409)
        credential = rotate_device_credential(self.owner, self.device)
        with self.client.websocket_connect("/devices/ws", headers={
            "Device-Id": self.device, "Authorization": f"Bearer {credential}",
        }) as socket, ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.client.post, path)
            message = socket.receive_json()
            self.assertEqual(message["payload"]["params"]["name"], "self.get_device_status")
            self.assertFalse(pending.done())
            socket.send_json({"type": "mcp", "payload": {
                "jsonrpc": "2.0", "id": message["payload"]["id"],
                "result": {"content": [{"type": "text", "text": "{\"audio_speaker\":{}}"}]},
            }})
            response = pending.result(timeout=6)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["acknowledged"])
