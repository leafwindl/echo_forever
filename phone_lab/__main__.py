from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


class PhoneLabError(RuntimeError):
    pass


def _find_adb() -> str:
    configured = os.environ.get("ECHO_ADB", "").strip()
    if configured:
        return configured
    found = shutil.which("adb")
    if found:
        return found
    roots = [
        os.environ.get("ANDROID_HOME", ""),
        os.environ.get("ANDROID_SDK_ROOT", ""),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"),
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "platform-tools" / (
            "adb.exe" if os.name == "nt" else "adb"
        )
        if candidate.is_file():
            return str(candidate)
    raise PhoneLabError(
        "找不到 adb。请安装 Android platform-tools，或设置 ECHO_ADB 指向 adb。"
    )


@dataclass
class Adb:
    serial: str = ""
    adb_path: str = field(default_factory=_find_adb)

    def _base(self) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        return command

    def run(self, *args: str, check: bool = True, binary: bool = False):
        completed = subprocess.run(
            [*self._base(), *args],
            capture_output=True,
            check=False,
            text=not binary,
            encoding=None if binary else "utf-8",
            errors=None if binary else "replace",
        )
        if check and completed.returncode != 0:
            stderr = (
                completed.stderr
                if isinstance(completed.stderr, str)
                else completed.stderr.decode("utf-8", "replace")
            )
            raise PhoneLabError(
                f"adb {' '.join(args)} 失败（{completed.returncode}）：{stderr.strip()}"
            )
        return completed.stdout

    def shell(self, *args: str, check: bool = True) -> str:
        return self.run("shell", *args, check=check)

    def devices(self) -> list[str]:
        output = subprocess.run(
            [self.adb_path, "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        ).stdout
        serials: list[str] = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials


def _resolve_serial(serial: str) -> str:
    adb = Adb(serial=serial)
    devices = adb.devices()
    if serial:
        if serial not in devices:
            raise PhoneLabError(f"设备 {serial} 当前不在线；在线设备：{devices}")
        return serial
    if len(devices) == 1:
        return devices[0]
    raise PhoneLabError(f"请用 --serial 指定设备；当前在线：{devices}")


@dataclass(frozen=True)
class UiNode:
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    package: str
    clickable: bool
    enabled: bool
    bounds: tuple[int, int, int, int] | None

    @property
    def center(self) -> tuple[int, int] | None:
        if not self.bounds:
            return None
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    def label(self) -> str:
        return self.text or self.content_desc or self.resource_id or self.class_name

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "content_desc": self.content_desc,
            "resource_id": self.resource_id,
            "class": self.class_name,
            "package": self.package,
            "clickable": self.clickable,
            "enabled": self.enabled,
            "bounds": list(self.bounds) if self.bounds else None,
            "center": list(self.center) if self.center else None,
        }


def parse_ui_xml(xml_text: str) -> list[UiNode]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PhoneLabError(f"UI XML 解析失败：{exc}") from exc
    nodes: list[UiNode] = []
    for node in root.iter("node"):
        bounds = None
        match = _BOUNDS_RE.search(node.get("bounds", ""))
        if match:
            bounds = tuple(int(value) for value in match.groups())
        nodes.append(
            UiNode(
                text=node.get("text", ""),
                content_desc=node.get("content-desc", ""),
                resource_id=node.get("resource-id", ""),
                class_name=node.get("class", ""),
                package=node.get("package", ""),
                clickable=node.get("clickable") == "true",
                enabled=node.get("enabled") == "true",
                bounds=bounds,
            )
        )
    return nodes


def _screen_size(adb: Adb) -> tuple[int, int]:
    output = adb.shell("wm", "size")
    match = re.search(r"(\d+)x(\d+)", output)
    if not match:
        raise PhoneLabError(f"无法读取屏幕尺寸：{output.strip()}")
    return int(match.group(1)), int(match.group(2))


def _current_activity(adb: Adb) -> str:
    output = adb.shell("dumpsys", "activity", "activities", check=False)
    for pattern in (
        r"topResumedActivity=ActivityRecord\{[^ ]+ u0 ([^ ]+)",
        r"mResumedActivity: ActivityRecord\{[^ ]+ u0 ([^ ]+)",
    ):
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return ""


def dump_ui(adb: Adb) -> tuple[str, list[UiNode]]:
    remote = "/sdcard/phone_lab_ui.xml"
    adb.shell("uiautomator", "dump", remote)
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        local = Path(handle.name)
    try:
        adb.run("pull", remote, str(local))
        xml_text = local.read_text(encoding="utf-8", errors="replace")
    finally:
        local.unlink(missing_ok=True)
        adb.shell("rm", "-f", remote, check=False)
    return xml_text, parse_ui_xml(xml_text)


def screenshot(adb: Adb, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = adb.run("exec-out", "screencap", "-p", binary=True)
    if not payload:
        raise PhoneLabError("截图为空，手机可能处于锁屏或黑屏。")
    path.write_bytes(payload)
    return path


def observe(adb: Adb, with_screenshot: bool = False) -> dict:
    width, height = _screen_size(adb)
    _, nodes = dump_ui(adb)
    screenshot_path = ""
    if with_screenshot:
        screenshot_path = str(
            screenshot(
                adb,
                ARTIFACT_DIR / f"observe-{int(time.time())}.png",
            )
        )
    return {
        "serial": adb.serial,
        "screen": {"width": width, "height": height},
        "current_activity": _current_activity(adb),
        "nodes": [node.as_dict() for node in nodes if node.label()],
        "screenshot": screenshot_path,
    }


def find_node(nodes: list[UiNode], query: str) -> UiNode:
    needle = query.casefold()
    matches = [
        node
        for node in nodes
        if needle in node.text.casefold()
        or needle in node.content_desc.casefold()
        or needle in node.resource_id.casefold()
    ]
    if not matches:
        raise PhoneLabError(f"没有找到包含“{query}”的界面元素。")
    clickable = [node for node in matches if node.clickable and node.center]
    return (clickable or matches)[0]


def tap_node(adb: Adb, query: str) -> UiNode:
    _, nodes = dump_ui(adb)
    node = find_node(nodes, query)
    if not node.center:
        raise PhoneLabError(f"元素“{query}”没有可点击坐标。")
    adb.shell("input", "tap", str(node.center[0]), str(node.center[1]))
    return node


def launch(adb: Adb, package: str) -> str:
    package = package.strip()
    if not package:
        raise PhoneLabError("包名不能为空。")
    adb.shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(20):
        activity = _current_activity(adb)
        if activity.startswith(package + "/"):
            return activity
        time.sleep(0.25)
    return _current_activity(adb)


def input_text(adb: Adb, text: str) -> None:
    if not text:
        raise PhoneLabError("输入文字不能为空。")
    if not text.isascii():
        raise PhoneLabError(
            "A1 的 ADB 基线只支持 ASCII 输入；中文输入留给 mobilerun / uiautomator2。"
        )
    escaped = text.replace(" ", "%s")
    adb.shell("input", "text", escaped)


def _find_mobilerun() -> str:
    configured = os.environ.get("ECHO_MOBILERUN", "").strip()
    if configured:
        return configured
    candidate = (
        Path(__file__).resolve().parent
        / ".venv"
        / "Scripts"
        / ("mobilerun.exe" if os.name == "nt" else "mobilerun")
    )
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("mobilerun")
    if found:
        return found
    raise PhoneLabError(
        "找不到 mobilerun。请在 phone_lab/.venv 安装 mobilerun，或设置 ECHO_MOBILERUN。"
    )


def task(
    adb: Adb,
    command: str,
    *,
    steps: int = 10,
    vision: bool = False,
    provider: str = "DeepSeek",
    model: str = "deepseek-v4-flash",
    timeout: int = 600,
) -> str:
    """把自然语言任务交给 mobilerun 的 FastAgent，并返回控制台输出。"""
    command = command.strip()
    if not command:
        raise PhoneLabError("任务描述不能为空。")
    executable = _find_mobilerun()
    args = [
        executable,
        "run",
        "--device",
        adb.serial,
        "--provider",
        provider,
        "--model",
        model,
        "--steps",
        str(steps),
        "--no-stream",
        "--no-vision" if not vision else "--vision",
        command,
    ]
    environment = os.environ.copy()
    adb_dir = str(Path(adb.adb_path).parent)
    environment["PATH"] = adb_dir + os.pathsep + environment.get("PATH", "")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PhoneLabError(f"mobilerun 任务超时（{timeout}s）。") from exc
    output = "\n".join(
        part for part in (completed.stdout, completed.stderr) if part
    ).strip()
    return output


def _print_nodes(nodes: list[UiNode], contains: str = "") -> None:
    needle = contains.casefold()
    for index, node in enumerate(nodes):
        if not node.label():
            continue
        if needle and needle not in (
            node.text + "\n" + node.content_desc + "\n" + node.resource_id
        ).casefold():
            continue
        center = node.center
        center_text = f"{center[0]},{center[1]}" if center else "-"
        print(
            f"{index:3d} {center_text:>11} "
            f"{'CLICK' if node.clickable else '     '} "
            f"{node.label()[:80]}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Echo phone_lab Android ADB 基线")
    parser.add_argument("--serial", default=os.environ.get("ECHO_ANDROID_SERIAL", ""))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出在线设备")
    sub.add_parser("current", help="显示当前前台 Activity")

    observe_parser = sub.add_parser("observe", help="读取屏幕、UI 树和可选截图")
    observe_parser.add_argument("--screenshot", action="store_true")

    ui_parser = sub.add_parser("ui", help="列出可读界面元素")
    ui_parser.add_argument("--contains", default="")

    tap_parser = sub.add_parser("tap", help="按坐标点击")
    tap_parser.add_argument("x", type=int)
    tap_parser.add_argument("y", type=int)

    tap_text_parser = sub.add_parser("tap-text", help="按文字/描述点击")
    tap_text_parser.add_argument("query")

    text_parser = sub.add_parser("text", help="输入 ASCII 文字")
    text_parser.add_argument("value")

    key_parser = sub.add_parser("key", help="发送按键：back/home/recents/enter")
    key_parser.add_argument("name", choices=("back", "home", "recents", "enter"))

    launch_parser = sub.add_parser("launch", help="启动应用包名")
    launch_parser.add_argument("package")

    task_parser = sub.add_parser("task", help="交给 mobilerun 执行自然语言任务")
    task_parser.add_argument("description")
    task_parser.add_argument("--steps", type=int, default=10)
    task_parser.add_argument("--vision", action="store_true")
    task_parser.add_argument("--provider", default="DeepSeek")
    task_parser.add_argument("--model", default="deepseek-v4-flash")

    shot_parser = sub.add_parser("screenshot", help="保存当前屏幕截图")
    shot_parser.add_argument("--path", default="")

    args = parser.parse_args(argv)
    adb = Adb(serial=args.serial)
    try:
        if args.command == "devices":
            print(json.dumps(adb.devices(), ensure_ascii=False))
            return 0
        if args.command == "current":
            print(_current_activity(adb))
            return 0
        if args.command == "observe":
            print(json.dumps(observe(adb, args.screenshot), ensure_ascii=False))
            return 0
        if args.command == "ui":
            _, nodes = dump_ui(adb)
            _print_nodes(nodes, args.contains)
            return 0
        if args.command == "tap":
            adb.shell("input", "tap", str(args.x), str(args.y))
            return 0
        if args.command == "tap-text":
            node = tap_node(adb, args.query)
            print(json.dumps(node.as_dict(), ensure_ascii=False))
            return 0
        if args.command == "text":
            input_text(adb, args.value)
            return 0
        if args.command == "key":
            key_codes = {
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
                "recents": "KEYCODE_APP_SWITCH",
                "enter": "KEYCODE_ENTER",
            }
            adb.shell("input", "keyevent", key_codes[args.name])
            return 0
        if args.command == "launch":
            print(launch(adb, args.package))
            return 0
        if args.command == "task":
            output = task(
                adb,
                args.description,
                steps=args.steps,
                vision=args.vision,
                provider=args.provider,
                model=args.model,
            )
            print(output)
            return 0 if "Goal achieved" in output else 1
        if args.command == "screenshot":
            target = (
                Path(args.path)
                if args.path
                else ARTIFACT_DIR / f"screenshot-{int(time.time())}.png"
            )
            print(screenshot(adb, target))
            return 0
    except PhoneLabError as exc:
        print(f"phone_lab: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
