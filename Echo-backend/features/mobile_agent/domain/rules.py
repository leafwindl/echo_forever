from __future__ import annotations

import hashlib
import secrets

PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8


def hash_secret(value: str, secret: str) -> str:
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()


def generate_pairing_code() -> str:
    return "".join(
        secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH)
    )


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_device_name(name: str) -> str:
    return name.strip()[:80] or "Echo 的手机"
