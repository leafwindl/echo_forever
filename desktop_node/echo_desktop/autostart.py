from __future__ import annotations

import sys
import winreg
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "EchoDesktop"


def autostart_command() -> str:
    """登录后启动的命令：优先用 pythonw，避免出现控制台窗口。"""
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    python = windowless if windowless.is_file() else executable
    launcher = Path(__file__).resolve().parent.parent / "launch_client.py"
    return f'"{python}" "{launcher}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _APP_NAME)
    except FileNotFoundError:
        return False
    return bool(str(value).strip())


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, autostart_command())
            return
        try:
            winreg.DeleteValue(key, _APP_NAME)
        except FileNotFoundError:
            pass
