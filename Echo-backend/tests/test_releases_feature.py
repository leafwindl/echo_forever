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
from shared.config import settings
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

    def get_active_by_id(self, release_id: str) -> AppRelease | None:
        if self.release and self.release.release_id == release_id:
            return self.release
        return None


class FakeStorage:
    def __init__(self):
        self.calls = []

    def download_url(
        self,
        object_key: str,
        expires_seconds: int,
        *,
        download_name: str | None = None,
    ) -> str:
        self.calls.append((object_key, expires_seconds, download_name))
        return "https://cos.example.test/signed-apk"

    def stream_bytes(self, object_key: str):
        self.calls.append(("stream", object_key))
        return iter([b"x" * 1024])


class ReleaseFeatureTests(unittest.TestCase):
    def setUp(self):
        request_limiter.reset()
        self.previous_auth_secret = settings.auth_token_secret
        self.previous_cos_custom_domain = settings.cos_custom_domain
        settings.auth_token_secret = "release-test-signing-secret"
        settings.cos_custom_domain = ""
        self.repository = FakeReleaseRepository(release_fixture())
        self.storage = FakeStorage()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_release_repository] = lambda: self.repository
        app.dependency_overrides[get_cos_object_storage] = lambda: self.storage
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        settings.auth_token_secret = self.previous_auth_secret
        settings.cos_custom_domain = self.previous_cos_custom_domain

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
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_latest_allows_the_public_site_origin_only(self):
        allowed = self.client.get(
            "/releases/latest",
            params={"version_code": 2},
            headers={"Origin": "https://echoaiforever.cn"},
        )
        denied = self.client.get(
            "/releases/latest",
            params={"version_code": 2},
            headers={"Origin": "https://untrusted.example"},
        )

        self.assertEqual(
            allowed.headers["access-control-allow-origin"],
            "https://echoaiforever.cn",
        )
        self.assertEqual(allowed.headers["vary"], "Origin")
        self.assertNotIn("access-control-allow-origin", denied.headers)

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
        self.assertIn(
            "/releases/release_test/artifact?",
            response.json()["download_url"],
        )

    def test_download_uses_cos_url_when_custom_domain_is_configured(self):
        settings.cos_custom_domain = "download.echoaiforever.cn"

        response = self.client.post(
            "/releases/release_test/download",
            json={"platform": "android", "channel": "internal", "version_code": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["download_url"],
            "https://cos.example.test/signed-apk",
        )
        self.assertEqual(
            self.storage.calls,
            [
                (
                    "echo/releases/android/internal/1.0.0+3/echo.apk",
                    settings.release_download_url_expires_seconds,
                    "Echo-v1.0.0.apk",
                )
            ],
        )

    def test_bootstrap_redirects_to_latest_signed_apk(self):
        response = self.client.get(
            "/releases/bootstrap/android",
            params={"channel": "internal"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 307)
        self.assertIn(
            "/releases/release_test/artifact?",
            response.headers["location"],
        )
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_artifact_streams_apk_with_download_headers(self):
        download = self.client.post(
            "/releases/release_test/download",
            json={"platform": "android", "channel": "internal", "version_code": 2},
        ).json()

        response = self.client.get(download["download_url"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"x" * 1024)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.android.package-archive",
        )
        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="Echo-v1.0.0.apk"',
        )

    def test_artifact_rejects_an_invalid_signature(self):
        response = self.client.get(
            "/releases/release_test/artifact",
            params={"expires": 4102444800, "signature": "0" * 64},
        )

        self.assertEqual(response.status_code, 403)

    def test_download_rejects_current_or_newer_client(self):
        response = self.client.post(
            "/releases/release_test/download",
            json={"platform": "android", "channel": "internal", "version_code": 3},
        )

        self.assertEqual(response.status_code, 404)

    def test_harmony_release_uses_hap_metadata_and_content_type(self):
        self.repository.release = release_fixture(
            platform="harmonyos",
            package_name="cn.echoaiforever.echo_app.dev",
            cos_object_key="echo/releases/harmonyos/internal/1.1.8+24/entry.hap",
        )
        latest = self.client.get(
            "/releases/latest",
            params={"platform": "harmonyos", "channel": "internal", "version_code": 2},
        )
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["release"]["platform"], "harmonyos")

        download = self.client.post(
            "/releases/release_test/download",
            json={"platform": "harmonyos", "channel": "internal", "version_code": 2},
        )
        self.assertEqual(download.status_code, 200)
        artifact = self.client.get(download.json()["download_url"])
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.headers["content-type"], "application/vnd.huawei.hap")
        self.assertEqual(
            artifact.headers["content-disposition"],
            'attachment; filename="Echo-v1.0.0.hap"',
        )


if __name__ == "__main__":
    unittest.main()
