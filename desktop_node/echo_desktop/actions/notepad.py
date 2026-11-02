from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes

from echo_desktop.protocol import ActionError

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


def _set_clipboard(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(0):
        raise ActionError("clipboard_unavailable", "剪贴板被其他程序占用了。")
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise ActionError("clipboard_unavailable", "无法分配剪贴板内存。")
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise ActionError("clipboard_unavailable", "无法写入剪贴板。")
    finally:
        user32.CloseClipboard()


def _find_notepad_window() -> int:
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        class_name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, class_name, 128)
        if class_name.value == "Notepad" or "记事本" in title or "Notepad" in title:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def _focus(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)


def _paste() -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def write_notepad(text: str) -> dict:
    content = str(text or "")
    if not content.strip():
        raise ActionError("empty_text", "没有要写进记事本的内容。")
    try:
        subprocess.Popen(["notepad.exe"])
    except OSError as exc:
        raise ActionError("notepad_failed", f"打开记事本失败：{exc}") from exc
    for _ in range(15):
        time.sleep(0.25)
        hwnd = _find_notepad_window()
        if hwnd:
            _focus(hwnd)
            time.sleep(0.2)
            _set_clipboard(content)
            _paste()
            return {"char_count": len(content), "preview": content[:120]}
    raise ActionError("notepad_not_found", "记事本打开了，但没有找到窗口。")
