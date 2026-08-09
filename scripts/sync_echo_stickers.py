from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
DEFAULT_ASSET_ROOT = PROJECT_ROOT / "assets" / "sticker"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from db.postgres_connection import transaction  # noqa: E402
from features.stickers.domain.services import validate_image  # noqa: E402
from features.stickers.public import backfill_sticker_embeddings  # noqa: E402
from shared.config import settings  # noqa: E402
from shared.storage import get_cos_object_storage  # noqa: E402

SUPPORTED_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class StickerAsset:
    path: Path
    semantic_tag: str
    content_type: str
    content_hash: str
    byte_size: int


def scan_assets(asset_root: Path) -> tuple[StickerAsset, ...]:
    if not asset_root.is_dir():
        raise FileNotFoundError(f"Sticker asset directory not found: {asset_root}")
    assets: list[StickerAsset] = []
    for path in sorted(asset_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_TYPES:
            continue
        content = path.read_bytes()
        content_type = SUPPORTED_TYPES[path.suffix.lower()]
        content_hash = validate_image(content, content_type, settings.sticker_upload_max_bytes)
        semantic_tag = path.stem.strip()
        if not semantic_tag:
            raise ValueError(f"Sticker filename must contain a semantic tag: {path.name}")
        assets.append(
            StickerAsset(
                path=path,
                semantic_tag=semantic_tag,
                content_type=content_type,
                content_hash=content_hash,
                byte_size=len(content),
            )
        )
    hashes = [asset.content_hash for asset in assets]
    if len(hashes) != len(set(hashes)):
        raise ValueError("The source directory contains duplicate sticker image content")
    return tuple(assets)


def sync_assets(asset_root: Path, *, apply: bool, priority: int) -> dict[str, object]:
    assets = scan_assets(asset_root)
    report: dict[str, object] = {"found": len(assets), "imported": [], "skipped": []}
    storage = get_cos_object_storage() if apply else None
    for asset in assets:
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sticker_id
                FROM stickers
                WHERE owner_type = 'echo' AND perceptual_hash = %s
                LIMIT 1
                """,
                (asset.content_hash,),
            )
            existing = cursor.fetchone()
        if existing is not None:
            report["skipped"].append(
                {
                    "file": asset.path.name,
                    "reason": "content_hash_exists",
                    "sticker_id": str(existing["sticker_id"]),
                }
            )
            continue
        if not apply:
            report["imported"].append(
                {"file": asset.path.name, "semantic_tag": asset.semantic_tag, "dry_run": True}
            )
            continue

        suffix = ".jpg" if asset.content_type == "image/jpeg" else asset.path.suffix.lower()
        relative_key = f"stickers/echo/official/{asset.content_hash[:24]}{suffix}"
        object_key = storage.put_bytes(
            relative_key,
            asset.path.read_bytes(),
            asset.content_type,
            cache_control="private, max-age=31536000, immutable",
        )
        sticker_id = f"stk_echo_{asset.content_hash[:24]}"
        with transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stickers (
                    sticker_id, owner_type, owner_user_id, source, storage_key,
                    public_url, content_type, byte_size, perceptual_hash, priority,
                    description, semantic_tags, status, moderation_status
                ) VALUES (
                    %s, 'echo', NULL, 'builtin', %s, '', %s, %s, %s, %s,
                    '', %s::jsonb, 'active', 'approved'
                )
                ON CONFLICT (sticker_id) DO NOTHING
                """,
                (
                    sticker_id,
                    object_key,
                    asset.content_type,
                    asset.byte_size,
                    asset.content_hash,
                    priority,
                    json.dumps([asset.semantic_tag], ensure_ascii=False),
                ),
            )
            inserted = cursor.rowcount == 1
        if inserted:
            report["imported"].append(
                {
                    "file": asset.path.name,
                    "semantic_tag": asset.semantic_tag,
                    "sticker_id": sticker_id,
                    "object_key": object_key,
                }
            )
        else:
            report["skipped"].append(
                {"file": asset.path.name, "reason": "sticker_id_exists", "sticker_id": sticker_id}
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally sync Echo official stickers")
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--priority", type=int, default=100)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload new objects to COS and register them in PostgreSQL",
    )
    args = parser.parse_args()
    if not 0 <= args.priority <= 10000:
        raise SystemExit("--priority must be between 0 and 10000")
    report = sync_assets(args.asset_root, apply=args.apply, priority=args.priority)
    if args.apply:
        report["embeddings_backfilled"] = asyncio.run(backfill_sticker_embeddings())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
