from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes

from echo_desktop.protocol import ActionError

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

_MEDIA_KEYS = {
    "play_pause": VK_MEDIA_PLAY_PAUSE,
    "next": VK_MEDIA_NEXT_TRACK,
    "previous": VK_MEDIA_PREV_TRACK,
}
_TARGET_MARKERS = ("网易云音乐", "CloudMusic")


def _cloudmusic_pids() -> set[int]:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq cloudmusic.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return set()
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        fields = line.strip().strip('"').split('","')
        if len(fields) < 2:
            continue
        try:
            pids.add(int(fields[1]))
        except ValueError:
            continue
    return pids


def _find_cloudmusic_window() -> int:
    user32 = ctypes.windll.user32
    pids = _cloudmusic_pids()
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pids and int(pid.value) not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if any(marker in buffer.value for marker in _TARGET_MARKERS):
                found.append(int(hwnd))
                return False
        class_name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, class_name, 128)
        if pids and class_name.value:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def _focus_window(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.ShowWindow(hwnd, 9)
    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached = False
    if target_thread and target_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))
    try:
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _is_cloudmusic_running() -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq cloudmusic.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return False
    return "cloudmusic.exe" in completed.stdout.lower()


def send_media_key(action: str) -> dict:
    key = _MEDIA_KEYS.get(action)
    if key is None:
        raise ActionError("unsupported_media_action", "不支持的媒体动作。")
    hwnd = _find_cloudmusic_window()
    if hwnd == 0 and not _is_cloudmusic_running():
        raise ActionError(
            "app_not_running",
            "没有找到正在运行的网易云音乐，请先让 Echo 打开它或手动打开。",
        )
    if hwnd:
        _focus_window(hwnd)
    user32 = ctypes.windll.user32
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
    return {"action": action, "target": "netease_cloud_music"}
