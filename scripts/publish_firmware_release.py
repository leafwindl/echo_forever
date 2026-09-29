from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from features.firmware_releases.infrastructure.postgres_repository import (  # noqa: E402
    PostgresFirmwareReleaseRepository,
)
from shared.storage import get_cos_object_storage  # noqa: E402

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
_SEMVER = re.compile(r"^\d+(?:\.\d+){1,3}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an Echo hardware firmware release")
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--board-type", required=True)
    parser.add_argument("--board-variant", default="")
    parser.add_argument("--version", required=True)
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args()

    firmware = args.firmware.resolve()
    if not firmware.is_file() or firmware.stat().st_size <= 0:
        raise SystemExit(f"Firmware not found or empty: {firmware}")
    if not args.board_type.strip() or not args.version.strip():
        raise SystemExit("--board-type and --version must not be empty")
    for name, value in (("--board-type", args.board_type), ("--board-variant", args.board_variant)):
        if value and not _SAFE_IDENTIFIER.fullmatch(value):
            raise SystemExit(f"{name} contains unsupported characters")
    if not _SEMVER.fullmatch(args.version.strip()):
        raise SystemExit("--version must be numeric semantic version, for example 0.1.4")

    repository = PostgresFirmwareReleaseRepository()
    existing = repository.get_by_version(args.board_type, args.board_variant, args.version)
    if existing is not None:
        raise SystemExit(
            f"Release already exists for {args.board_type}/{args.board_variant} "
            f"version={args.version}: {existing.release_id}"
        )

    digest = _sha256(firmware)
    size_bytes = firmware.stat().st_size
    relative_key = (
        f"releases/firmware/{args.board_type}/{args.board_variant or 'generic'}/"
        f"{args.version}/echo-{digest[:12]}.bin"
    )
    storage = get_cos_object_storage()
    object_key = storage.put_file(
        relative_key,
        firmware,
        "application/octet-stream",
        cache_control="private, max-age=31536000, immutable",
    )
    try:
        metadata = storage.head(object_key)
        if metadata.content_length != size_bytes:
            raise RuntimeError(
                f"COS size mismatch: expected {size_bytes}, got {metadata.content_length}"
            )
        release = repository.publish(
            board_type=args.board_type.strip(),
            board_variant=args.board_variant.strip(),
            version=args.version.strip(),
            cos_object_key=object_key,
            sha256=digest,
            size_bytes=size_bytes,
            release_notes=args.note,
        )
    except Exception:
        storage.delete(object_key)
        raise

    print(
        f"Published {release.release_id}: {args.board_type} "
        f"{args.version} ({size_bytes} bytes, sha256={digest})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
