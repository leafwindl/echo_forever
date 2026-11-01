"""Seed the built-in sticker pack into the current database.

This is a local/dev provisioning tool. It copies the repository's built-in
sticker images into the backend static directory and upserts their metadata.
It never deletes existing stickers or touches user-owned rows.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))

from db.postgres_connection import transaction  # noqa: E402
from features.stickers.public import backfill_sticker_embeddings  # noqa: E402

STICKERS = {
    "加油": ("加油打气", ("加油", "鼓励", "支持", "打气")),
    "嘿嘿": ("嘿嘿坏笑", ("嘿嘿", "得意", "坏笑", "开心")),
    "开心": ("开心庆祝", ("开心", "高兴", "庆祝", "笑")),
    "我来了": ("我来了", ("我来了", "到场", "出现", "打招呼")),
    "收到": ("收到明白", ("收到", "OK", "明白", "答应")),
    "早安": ("早安问候", ("早安", "早上好", "问候")),
    "晚安": ("晚安关心", ("晚安", "睡觉", "夜晚", "关心")),
    "期待": ("期待盼望", ("期待", "盼望", "兴奋")),
    "生气": ("生气不满", ("生气", "不满", "哼", "吃醋")),
    "疑惑": ("疑惑不解", ("疑惑", "问号", "不解", "困惑")),
    "难过": ("难过安慰", ("难过", "伤心", "安慰", "低落")),
}

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _seed(base_url: str, public_url_only: bool = False) -> int:
    source_dir = PROJECT_ROOT / "assets" / "sticker"
    target_dir = BACKEND_ROOT / "static" / "stickers"
    target_dir.mkdir(parents=True, exist_ok=True)
    seeded = 0
    with transaction() as conn, conn.cursor() as cursor:
        for stem, (description, tags) in STICKERS.items():
            matches = sorted(source_dir.glob(f"{stem}.*"))
            if not matches:
                print(f"skip missing asset: {stem}")
                continue
            source = matches[0]
            content = source.read_bytes()
            content_type = _CONTENT_TYPES.get(source.suffix.lower())
            if content_type is None:
                print(f"skip unsupported asset: {source.name}")
                continue
            digest = hashlib.sha256(content).hexdigest()
            filename = f"{digest}{source.suffix.lower()}"
            target = target_dir / filename
            if not target.exists():
                shutil.copyfile(source, target)
            sticker_id = f"stk_official_{stem}"
            public_url = f"{base_url.rstrip('/')}/static/stickers/{filename}"
            storage_key = "" if public_url_only else f"stickers/{filename}"
            cursor.execute(
                """
                INSERT INTO stickers (
                    sticker_id, owner_type, owner_user_id, source, storage_key,
                    public_url, content_type, byte_size, perceptual_hash,
                    description, semantic_tags, status, moderation_status, priority
                ) VALUES (
                    %s, 'echo', NULL, 'builtin', %s, %s, %s, %s, %s,
                    %s, %s::jsonb, 'active', 'approved', 80
                )
                ON CONFLICT (sticker_id) DO UPDATE SET
                    storage_key = EXCLUDED.storage_key,
                    public_url = EXCLUDED.public_url,
                    content_type = EXCLUDED.content_type,
                    byte_size = EXCLUDED.byte_size,
                    perceptual_hash = EXCLUDED.perceptual_hash,
                    description = EXCLUDED.description,
                    semantic_tags = EXCLUDED.semantic_tags,
                    status = 'active',
                    moderation_status = 'approved',
                    updated_at = NOW()
                """,
                (
                    sticker_id,
                    storage_key,
                    public_url,
                    content_type,
                    len(content),
                    digest,
                    description,
                    json.dumps(list(tags), ensure_ascii=False),
                ),
            )
            seeded += 1
    return seeded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Public backend base URL used to build static sticker URLs.",
    )
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument(
        "--public-url-only",
        action="store_true",
        help="Serve stickers from the local public URL instead of signing COS URLs.",
    )
    args = parser.parse_args()
    count = _seed(args.base_url, public_url_only=args.public_url_only)
    print(f"seeded {count} official stickers")
    if not args.skip_embeddings:
        embedded = asyncio.run(backfill_sticker_embeddings())
        print(f"backfilled {embedded} sticker embeddings")


if __name__ == "__main__":
    main()
