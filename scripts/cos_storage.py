from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from shared.storage import (  # noqa: E402
    CosStorageConfigurationError,
    get_cos_object_storage,
)


def smoke_test() -> None:
    storage = get_cos_object_storage()
    payload = f"echo-cos-smoke-test:{uuid.uuid4().hex}".encode()
    relative_key = f"smoke-tests/{uuid.uuid4().hex}.txt"
    object_key = storage.put_bytes(relative_key, payload, "text/plain; charset=utf-8")
    try:
        metadata = storage.head(object_key)
        if metadata.content_length != len(payload):
            raise RuntimeError(
                f"COS size mismatch: expected {len(payload)}, got {metadata.content_length}"
            )
        signed_url = storage.download_url(object_key, expires_seconds=300)
        with urlopen(signed_url, timeout=30) as response:  # noqa: S310
            downloaded = response.read()
        if downloaded != payload:
            raise RuntimeError("COS downloaded content does not match the uploaded content")
        print(f"COS smoke test passed: bucket={storage.bucket} object={object_key}")
    finally:
        storage.delete(object_key)


def upload_reference_assets() -> None:
    storage = get_cos_object_storage()
    assets = {
        "reference/character/echo-idle-v1.png": (
            PROJECT_ROOT / "app" / "assets" / "character" / "echo_idle.png"
        ),
        "reference/character/echo-sit-v1.png": (
            PROJECT_ROOT / "app" / "assets" / "character" / "idle_sit.png"
        ),
    }
    for relative_key, source in assets.items():
        if not source.is_file():
            raise FileNotFoundError(f"Reference asset not found: {source}")
        object_key = storage.put_bytes(
            relative_key,
            source.read_bytes(),
            "image/png",
            cache_control="private, max-age=86400",
        )
        print(f"Uploaded reference asset: {source.name} -> {object_key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Echo COS setup utilities")
    parser.add_argument(
        "command",
        choices=("smoke-test", "upload-reference-assets"),
        help="Operation to run after COS credentials have been configured",
    )
    args = parser.parse_args()
    try:
        if args.command == "smoke-test":
            smoke_test()
        else:
            upload_reference_assets()
    except CosStorageConfigurationError as exc:
        raise SystemExit(f"COS configuration error: {exc}") from None


if __name__ == "__main__":
    main()
