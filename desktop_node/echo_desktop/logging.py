from __future__ import annotations

from datetime import datetime
from pathlib import Path

from echo_desktop.config import data_dir

MAX_LOG_BYTES = 1_000_000


def log_path() -> Path:
    return data_dir() / "echo-desktop.log"


def append_log(level: str, message: str) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = log_path()
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        rotated = path.with_suffix(".old.log")
        path.replace(rotated)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [{level}] {message}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
