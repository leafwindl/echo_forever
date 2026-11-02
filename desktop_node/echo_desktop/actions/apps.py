from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from echo_desktop.protocol import ActionError

APP_LABELS = {
    "netease_cloud_music": "网易云音乐",
    "notepad": "记事本",
    "calculator": "计算器",
}

_NETEASE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Netease\CloudMusic\cloudmusic.exe"),
    Path(r"C:\Program Files\Netease\CloudMusic\cloudmusic.exe"),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Netease\CloudMusic\cloudmusic.exe")),
    Path(os.path.expandvars(r"%PROGRAMFILES(X86)%\Netease\CloudMusic\cloudmusic.exe")),
)


def _find_netease() -> Path | None:
    for candidate in _NETEASE_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("cloudmusic.exe") or shutil.which("cloudmusic")
    if found:
        return Path(found)
    try:
        import winreg
    except ImportError:
        return None
    uninstall_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    )
    for root, path in uninstall_roots:
        try:
            with winreg.OpenKey(root, path) as uninstall:
                for index in range(winreg.QueryInfoKey(uninstall)[0]):
                    try:
                        name = winreg.EnumKey(uninstall, index)
                        with winreg.OpenKey(uninstall, name) as app_key:
                            display_name = str(
                                winreg.QueryValueEx(app_key, "DisplayName")[0]
                            )
                            if (
                                "网易云音乐" not in display_name
                                and "CloudMusic" not in display_name
                            ):
                                continue
                            for value_name in ("InstallLocation", "DisplayIcon"):
                                try:
                                    location = str(
                                        winreg.QueryValueEx(app_key, value_name)[0]
                                    ).strip().strip('"')
                                except OSError:
                                    continue
                                candidate = Path(location)
                                if candidate.suffix.lower() != ".exe":
                                    candidate = candidate / "cloudmusic.exe"
                                if candidate.is_file():
                                    return candidate
                            try:
                                uninstall = str(
                                    winreg.QueryValueEx(app_key, "UninstallString")[0]
                                ).strip().strip('"')
                            except OSError:
                                continue
                            candidate = Path(uninstall).parent / "cloudmusic.exe"
                            if candidate.is_file():
                                return candidate
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def resolve_app(app: str) -> str:
    if app == "netease_cloud_music":
        path = _find_netease()
        if path is None:
            raise ActionError(
                "app_not_found",
                "没有找到网易云音乐，请确认已安装，或把安装路径告诉开发同学。",
            )
        return str(path)
    if app == "notepad":
        return "notepad.exe"
    if app == "calculator":
        return "calc.exe"
    raise ActionError("unsupported_app", "这个应用不在允许列表里。")


def launch_app(app: str) -> dict:
    executable = resolve_app(app)
    if not Path(executable).is_file() and executable.endswith(".exe") and "\\" in executable:
        raise ActionError("app_not_found", f"找不到可执行文件：{executable}")
    try:
        process = subprocess.Popen([executable])
    except OSError as exc:
        raise ActionError("app_launch_failed", f"打开应用失败：{exc}") from exc
    return {
        "app": app,
        "label": APP_LABELS.get(app, app),
        "pid": process.pid,
    }
