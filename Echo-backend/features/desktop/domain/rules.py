from __future__ import annotations

import hashlib
import hmac
import secrets

from features.desktop.domain.entities import ALLOWED_APPS, MEDIA_ACTIONS


def normalize_pairing_code(code: str) -> str:
    cleaned = "".join(character for character in code if character.isdigit())
    if len(cleaned) != 6:
        raise ValueError("Pairing code must contain six digits")
    return cleaned


def generate_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def pairing_code_hash(code: str, secret: str) -> str:
    normalized = normalize_pairing_code(code)
    return hmac.new(
        secret.encode("utf-8"),
        f"desktop-pair:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()


def node_token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def generate_node_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_capabilities(capabilities: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    allowed = {
        "open_app",
        "media_control",
        "screen_capture",
        "camera_capture",
    }
    return tuple(dict.fromkeys(item for item in capabilities if item in allowed))


def validate_action_arguments(action: str, arguments: dict) -> dict:
    if action == "open_app":
        app = str(arguments.get("app") or "").strip()
        if app not in ALLOWED_APPS:
            raise ValueError("unsupported app")
        return {"app": app}
    if action == "media_control":
        media_action = str(arguments.get("action") or "").strip()
        if media_action not in MEDIA_ACTIONS:
            raise ValueError("unsupported media action")
        return {"action": media_action}
    if action in {"screen_capture", "camera_capture"}:
        question = str(arguments.get("question") or "").strip()
        return {"question": question[:300]}
    raise ValueError("unsupported desktop action")
