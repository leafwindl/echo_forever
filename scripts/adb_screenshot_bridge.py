"""Local ADB screenshot bridge for the Echo Phone Agent.

Run this on the PC that has the test phone connected over USB. The bridge
captures the phone screen with `adb exec-out screencap -p` and exposes it on
localhost. The phone reaches it through `adb reverse tcp:8765 tcp:8765`.

This is a development fallback for devices where MediaProjection is blocked by
the OEM. It is intentionally bound to 127.0.0.1 and is not a production server.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import struct
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_ADB = Path(
    r"C:\Users\leafwind\AppData\Local\Android\Sdk\platform-tools\adb.exe"
)


def resolve_adb(explicit: str | None) -> str:
    if explicit:
        return explicit
    if DEFAULT_ADB.exists():
        return str(DEFAULT_ADB)
    discovered = shutil.which("adb")
    if discovered:
        return discovered
    raise SystemExit("adb not found; pass --adb or put adb on PATH")


def png_size(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    width, height = struct.unpack(">II", payload[16:24])
    return width, height


class Bridge:
    def __init__(self, adb: str, serial: str | None):
        self.adb = adb
        self.serial = serial

    def _base(self) -> list[str]:
        command = [self.adb]
        if self.serial:
            command.extend(["-s", self.serial])
        return command

    def reverse(self, port: int) -> None:
        subprocess.run(
            self._base() + ["reverse", f"tcp:{port}", f"tcp:{port}"],
            check=True,
            capture_output=True,
            text=True,
        )

    def screenshot(self) -> bytes:
        result = subprocess.run(
            self._base() + ["exec-out", "screencap", "-p"],
            check=True,
            capture_output=True,
        )
        payload = result.stdout
        if not payload.startswith(b"\x89PNG"):
            raise RuntimeError("adb screencap did not return a PNG")
        return payload

    def type_text(self, text: str) -> None:
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        subprocess.run(
            self._base() + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            self._base()
            + [
                "shell",
                "am",
                "broadcast",
                "-a",
                "ADB_INPUT_B64",
                "--es",
                "msg",
                encoded,
            ],
            check=True,
            capture_output=True,
        )

    def keyevent(self, keycode: int) -> None:
        subprocess.run(
            self._base() + ["shell", "input", "keyevent", str(keycode)],
            check=True,
            capture_output=True,
        )

    def launch_app(self, package: str) -> None:
        subprocess.run(
            self._base()
            + [
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            check=True,
            capture_output=True,
        )

    def open_uri(self, uri: str) -> None:
        if not (
            uri.startswith("http://")
            or uri.startswith("https://")
            or uri.startswith("orpheus://")
            or uri.startswith("bilibili://")
            or uri.startswith("snssdk1128://")
        ):
            raise ValueError("unsupported uri scheme")
        subprocess.run(
            self._base()
            + ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", uri],
            check=True,
            capture_output=True,
        )

    def ensure_keyboard(self) -> None:
        component = "com.android.adbkeyboard/.AdbIME"
        subprocess.run(
            self._base() + ["shell", "ime", "enable", component],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            self._base() + ["shell", "ime", "set", component],
            check=False,
            capture_output=True,
        )


class Handler(BaseHTTPRequestHandler):
    bridge: Bridge

    def _json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._json(200, {"ok": True, "service": "echo-adb-screenshot-bridge"})
            return
        if self.path.rstrip("/") != "/screenshot":
            self._json(404, {"error": "not_found"})
            return
        try:
            payload = self.bridge.screenshot()
        except Exception as exc:
            self._json(503, {"error": "screenshot_failed", "detail": str(exc)})
            return
        width, height = png_size(payload)
        self._json(
            200,
            {
                "mime": "image/png",
                "width": width,
                "height": height,
                "image_base64": base64.b64encode(payload).decode("ascii"),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {
            "/text",
            "/key",
            "/open_uri",
            "/launch_app",
        }:
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json(400, {"error": "invalid_json"})
            return
        try:
            if self.path.rstrip("/") == "/text":
                text = str(body.get("text") or "")
                if not text or len(text) > 2000:
                    self._json(400, {"error": "invalid_text"})
                    return
                self.bridge.type_text(text)
                self._json(200, {"ok": True, "source": "adb_keyboard"})
                return
            if self.path.rstrip("/") == "/open_uri":
                uri = str(body.get("uri") or "")
                self.bridge.open_uri(uri)
                self._json(200, {"ok": True, "uri": uri})
                return
            if self.path.rstrip("/") == "/launch_app":
                package = str(body.get("package") or "")
                if not package or len(package) > 200:
                    self._json(400, {"error": "invalid_package"})
                    return
                self.bridge.launch_app(package)
                self._json(200, {"ok": True, "package": package})
                return
            keycode = int(body.get("keycode") or 0)
            if keycode <= 0:
                self._json(400, {"error": "invalid_keycode"})
                return
            self.bridge.keyevent(keycode)
            self._json(200, {"ok": True, "keycode": keycode})
        except Exception as exc:
            self._json(503, {"error": "input_failed", "detail": str(exc)})

    def log_message(self, format: str, *args) -> None:
        print(f"[adb-bridge] {format % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Echo ADB screenshot bridge")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--adb", default=None)
    parser.add_argument(
        "--no-reverse",
        action="store_true",
        help="Do not run adb reverse; use when setting it up yourself.",
    )
    args = parser.parse_args()

    bridge = Bridge(resolve_adb(args.adb), args.serial)
    bridge.ensure_keyboard()
    if not args.no_reverse:
        try:
            bridge.reverse(args.port)
            print(
                f"[adb-bridge] adb reverse tcp:{args.port} -> tcp:{args.port}",
                flush=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"[adb-bridge] reverse failed: {exc.stderr}", flush=True)

    Handler.bridge = bridge
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"[adb-bridge] listening on http://127.0.0.1:{args.port} "
        f"(phone: http://127.0.0.1:{args.port}/screenshot)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
