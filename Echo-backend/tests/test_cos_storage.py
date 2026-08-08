import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from shared.storage.cos_storage import (
    CosObjectStorage,
    CosStorageConfig,
    CosStorageConfigurationError,
    normalize_cos_custom_domain,
    resolve_cos_credentials,
)


class FakeCosClient:
    def __init__(self):
        self.calls = []
        self.last_body = None

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs))

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs))
        return {
            "Content-Length": "4",
            "Content-Type": "image/png",
            "ETag": '"abc123"',
        }

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs))

    def get_presigned_url(self, **kwargs):
        self.calls.append(("signed_url", kwargs))
        return "https://example.test/signed"

    def get_object_url(self, **kwargs):
        self.calls.append(("object_url", kwargs))
        return "https://example.test/public"

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        self.last_body = FakeStreamBody([b"ab", b"cd"])
        return {"Body": self.last_body}


class FakeRawStream:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeStreamBody:
    def __init__(self, chunks):
        self.chunks = chunks
        self.raw = FakeRawStream()

    def get_stream(self, chunk_size):
        del chunk_size
        return iter(self.chunks)

    def get_raw_stream(self):
        return self.raw


def storage_config(**overrides):
    values = {
        "bucket": "echo-1438300232",
        "region": "ap-guangzhou",
        "secret_id": "test-secret-id",
        "secret_key": "test-secret-key",
        "object_prefix": "echo",
    }
    values.update(overrides)
    return CosStorageConfig(**values)


class CosObjectStorageTests(unittest.TestCase):
    def test_configuration_requires_credentials(self):
        with self.assertRaises(CosStorageConfigurationError):
            CosObjectStorage(storage_config(secret_key=""), client=FakeCosClient())

    def test_custom_domain_accepts_host_or_https_url(self):
        self.assertEqual(normalize_cos_custom_domain("img.example.com"), "img.example.com")
        self.assertEqual(
            normalize_cos_custom_domain("https://img.example.com/"),
            "img.example.com",
        )

    def test_custom_domain_rejects_http(self):
        with self.assertRaises(CosStorageConfigurationError):
            normalize_cos_custom_domain("http://img.example.com")

    def test_configuration_rejects_unsafe_prefix(self):
        with self.assertRaises(CosStorageConfigurationError):
            CosObjectStorage(storage_config(object_prefix="echo/../secret"), client=FakeCosClient())

    def test_upload_prefixes_key_and_keeps_bucket_private(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(), client=client)

        object_key = storage.put_bytes("letters/letter-1.webp", b"data", "image/webp")

        self.assertEqual(object_key, "echo/letters/letter-1.webp")
        self.assertEqual(client.calls[0][0], "put")
        self.assertEqual(client.calls[0][1]["Bucket"], "echo-1438300232")
        self.assertNotIn("ACL", client.calls[0][1])

    def test_object_key_rejects_parent_traversal(self):
        storage = CosObjectStorage(storage_config(), client=FakeCosClient())
        with self.assertRaises(ValueError):
            storage.object_key("letters/../secret.txt")

    def test_upload_rejects_empty_content_type(self):
        storage = CosObjectStorage(storage_config(), client=FakeCosClient())
        with self.assertRaises(ValueError):
            storage.put_bytes("letters/letter-1.webp", b"data", "")

    def test_put_file_streams_from_disk(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(), client=client)
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "echo.apk"
            path.write_bytes(b"apk-data")

            object_key = storage.put_file(
                "releases/android/internal/1.0.0+3/echo.apk",
                path,
                "application/vnd.android.package-archive",
            )

        self.assertEqual(
            object_key,
            "echo/releases/android/internal/1.0.0+3/echo.apk",
        )
        body = client.calls[0][1]["Body"]
        self.assertNotIsInstance(body, bytes)
        self.assertTrue(body.closed)

    def test_head_returns_normalized_metadata(self):
        storage = CosObjectStorage(storage_config(), client=FakeCosClient())
        metadata = storage.head("letters/letter-1.webp")
        self.assertEqual(metadata.object_key, "echo/letters/letter-1.webp")
        self.assertEqual(metadata.content_length, 4)
        self.assertEqual(metadata.etag, "abc123")

    def test_private_bucket_uses_short_lived_signed_url(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(private_read=True), client=client)
        url = storage.download_url("letters/letter-1.webp", expires_seconds=300)
        self.assertEqual(url, "https://example.test/signed")
        self.assertEqual(client.calls[-1][1]["Expired"], 300)

    def test_private_download_can_override_the_response_filename(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(private_read=True), client=client)

        storage.download_url(
            "releases/echo.apk",
            expires_seconds=300,
            download_name="Echo-v1.0.6.apk",
        )

        self.assertEqual(
            client.calls[-1][1]["Params"],
            {
                "response-content-disposition": (
                    'attachment; filename="Echo-v1.0.6.apk"'
                )
            },
        )

    def test_download_filename_rejects_unsafe_characters(self):
        storage = CosObjectStorage(storage_config(private_read=True), client=FakeCosClient())
        with self.assertRaises(ValueError):
            storage.download_url(
                "releases/echo.apk",
                download_name='Echo-v1.0.6\r\nunsafe.apk',
            )

    def test_private_bucket_rejects_zero_expiration(self):
        storage = CosObjectStorage(storage_config(private_read=True), client=FakeCosClient())
        with self.assertRaises(ValueError):
            storage.download_url("letters/letter-1.webp", expires_seconds=0)

    def test_public_bucket_uses_plain_object_url(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(private_read=False), client=client)
        url = storage.download_url("letters/letter-1.webp")
        self.assertEqual(url, "https://example.test/public")

    def test_public_download_can_override_the_response_filename(self):
        storage = CosObjectStorage(
            storage_config(private_read=False),
            client=FakeCosClient(),
        )
        url = storage.download_url(
            "releases/echo.apk",
            download_name="Echo-v1.0.6.apk",
        )
        self.assertIn("response-content-disposition=", url)
        self.assertIn("Echo-v1.0.6.apk", url)

    def test_stream_bytes_closes_the_cos_response(self):
        client = FakeCosClient()
        storage = CosObjectStorage(storage_config(), client=client)

        content = b"".join(storage.stream_bytes("releases/echo.apk", chunk_size=2))

        self.assertEqual(content, b"abcd")
        self.assertEqual(client.calls[-1][0], "get")
        self.assertTrue(client.calls[-1][1]["Key"].endswith("releases/echo.apk"))
        self.assertTrue(client.last_body.raw.closed)

    def test_explicit_cos_credentials_take_precedence(self):
        with (
            patch("shared.storage.cos_storage.settings.cos_secret_id", "cos-id"),
            patch("shared.storage.cos_storage.settings.cos_secret_key", "cos-key"),
            patch("shared.storage.cos_storage.settings.tencent_secret_id", "asr-id"),
            patch("shared.storage.cos_storage.settings.tencent_secret_key", "asr-key"),
            patch("shared.storage.cos_storage.settings.cos_reuse_tencent_credentials", True),
        ):
            self.assertEqual(resolve_cos_credentials(), ("cos-id", "cos-key"))

    def test_asr_credentials_can_be_reused_only_when_explicitly_enabled(self):
        with (
            patch("shared.storage.cos_storage.settings.cos_secret_id", ""),
            patch("shared.storage.cos_storage.settings.cos_secret_key", ""),
            patch("shared.storage.cos_storage.settings.tencent_secret_id", "asr-id"),
            patch("shared.storage.cos_storage.settings.tencent_secret_key", "asr-key"),
            patch("shared.storage.cos_storage.settings.cos_reuse_tencent_credentials", True),
        ):
            self.assertEqual(resolve_cos_credentials(), ("asr-id", "asr-key"))

    def test_partial_cos_credentials_never_mix_with_asr_credentials(self):
        with (
            patch("shared.storage.cos_storage.settings.cos_secret_id", "cos-id"),
            patch("shared.storage.cos_storage.settings.cos_secret_key", ""),
            patch("shared.storage.cos_storage.settings.cos_reuse_tencent_credentials", True),
            self.assertRaises(CosStorageConfigurationError),
        ):
            resolve_cos_credentials()


if __name__ == "__main__":
    unittest.main()
