from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def data_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "EchoDesktop"
    return Path.home() / ".echo_desktop"


def config_path() -> Path:
    return data_dir() / "config.json"


@dataclass(frozen=True)
class DesktopConfig:
    server_url: str
    node_id: str
    node_name: str
    token: str
    auto_approve: bool = True

    @property
    def websocket_url(self) -> str:
        base = self.server_url.rstrip("/")
        if base.startswith("https://"):
            base = "wss://" + base.removeprefix("https://")
        elif base.startswith("http://"):
            base = "ws://" + base.removeprefix("http://")
        return base + "/desktop/nodes/ws"


def load_config() -> DesktopConfig | None:
    path = config_path()
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DesktopConfig(
        server_url=str(payload["server_url"]),
        node_id=str(payload["node_id"]),
        node_name=str(payload["node_name"]),
        token=str(payload["token"]),
        auto_approve=bool(payload.get("auto_approve", True)),
    )


def save_config(config: DesktopConfig) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = config_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def clear_config() -> None:
    path = config_path()
    if path.exists():
        path.unlink()
