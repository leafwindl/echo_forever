import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.releases.domain.entities import AppRelease
from features.releases.interface.router import (
    get_release_repository,
    router,
)
from shared.security import request_limiter
from shared.storage import get_cos_object_storage


def release_fixture(**overrides) -> AppRelease:
    values = {
        "release_id": "release_test",
        "platform": "android",
        "channel": "internal",
        "package_name": "cn.echoaiforever.echo_app",
        "version_name": "1.0.0",
        "version_code": 3,
        "minimum_version_code": 2,
        "cos_object_key": "echo/releases/android/internal/1.0.0+3/echo.apk",
        "sha256": "a" * 64,
        "size_bytes": 1024,
        "release_notes": ("支持应用内更新",),
        "mandatory": False,
        "status": "active",
        "published_at": datetime(2026, 8, 6, tzinfo=UTC),
    }
    values.update(overrides)
    return AppRelease(**values)


class FakeReleaseRepository:
    def __init__(self, release: AppRelease | None):
        self.release = release

    def find_latest(self, platform: str, channel: str) -> AppRelease | None:
        if self.release and (self.release.platform, self.release.channel) == (platform, channel):
            return self.release
        return None

    def get_active(self, release_id: str, platform: str, channel: str) -> AppRelease | None:
        release = self.find_latest(platform, channel)
        if release and release.release_id == release_id and release.status == "active":
            return release
        return None


class FakeStorage:
    def __init__(self):
        self.calls = []

    def download_url(self, object_key: str, expires_seconds: int) -> str:
        self.calls.append((object_key, expires_seconds))
        return "https://cos.example.test/signed-apk"


class ReleaseFeatureTests(unittest.TestCase):
    def setUp(self):
        request_limiter.reset()
        self.repository = FakeReleaseRepository(release_fixture())
        self.storage = FakeStorage()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_release_repository] = lambda: self.repository
        app.dependency_overrides[get_cos_object_storage] = lambda: self.storage
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_latest_returns_metadata_without_download_url(self):
        response = self.client.get(
            "/releases/latest",
            params={"platform": "android", "channel": "internal", "version_code": 2},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["update_available"])
        self.assertEqual(body["release"]["version_code"], 3)
        self.assertNotIn("download_url", body["release"])

    def test_minimum_version_makes_update_mandatory(self):
        response = self.client.get(
            "/releases/latest",
            params={"platform": "android", "channel": "internal", "version_code": 1},
        )

        self.assertTrue(response.json()["release"]["mandatory"])

    def test_current_version_reports_no_update(self):
        response = self.client.get(
            "/releases/latest",
            params={"platform": "android", "channel": "internal", "version_code": 3},
        )

        self.assertEqual(response.json(), {"update_available": False, "release": None})

    def test_download_mints_short_lived_url(self):
        response = self.client.post(
            "/releases/release_test/download",
            json={"platform": "android", "channel": "internal", "version_code": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["download_url"], "https://cos.example.test/signed-apk")
        self.assertEqual(self.storage.calls[0][0], self.repository.release.cos_object_key)

    def test_download_rejects_current_or_newer_client(self):
        response = self.client.post(
            "/releases/release_test/download",
            json={"platform": "android", "channel": "internal", "version_code": 3},
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
