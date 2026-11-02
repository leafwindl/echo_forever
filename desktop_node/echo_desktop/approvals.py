from __future__ import annotations

import ctypes
import sys

MB_ICONQUESTION = 0x00000020
MB_ICONWARNING = 0x00000030
MB_YESNO = 0x00000004
MB_TOPMOST = 0x00040000
MB_SETFOREGROUND = 0x00010000
IDYES = 6


def ask_windows_approval(title: str, message: str, *, warning: bool = False) -> bool:
    if sys.platform != "win32":
        return False
    flags = MB_YESNO | MB_TOPMOST | MB_SETFOREGROUND
    flags |= MB_ICONWARNING if warning else MB_ICONQUESTION
    result = ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    return result == IDYES
