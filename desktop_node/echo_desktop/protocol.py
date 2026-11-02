from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ActionError(RuntimeError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass(frozen=True)
class Command:
    command_id: str
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 45


def parse_command(payload: dict[str, Any]) -> Command:
    command_id = str(payload.get("command_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not command_id or not action:
        raise ValueError("command_id and action are required")
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        timeout_seconds = int(payload.get("timeout_seconds") or 45)
    except (TypeError, ValueError):
        timeout_seconds = 45
    return Command(
        command_id=command_id,
        action=action,
        arguments=arguments,
        timeout_seconds=max(5, min(timeout_seconds, 120)),
    )


def result_payload(
    command_id: str,
    *,
    data: dict[str, Any] | None = None,
    error: ActionError | None = None,
) -> dict[str, Any]:
    if error is not None:
        return {
            "type": "result",
            "command_id": command_id,
            "ok": False,
            "error": {"code": error.code, "message": error.message},
        }
    return {
        "type": "result",
        "command_id": command_id,
        "ok": True,
        "data": data or {},
    }
