from __future__ import annotations

import ctypes
import time

from echo_desktop.actions.media import _find_cloudmusic_window, _focus_window
from echo_desktop.actions.notepad import _set_clipboard
from echo_desktop.protocol import ActionError

VK_CONTROL = 0x11
VK_F = 0x46
VK_V = 0x56
VK_RETURN = 0x0D
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _combo(control: int, key: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(control, 0, 0, 0)
    _key(key)
    user32.keybd_event(control, 0, KEYEVENTF_KEYUP, 0)


def search_and_play(query: str) -> dict:
    song = " ".join(str(query or "").split()).strip()
    if not song:
        raise ActionError("empty_query", "没有要搜索的歌曲。")
    hwnd = _find_cloudmusic_window()
    if hwnd == 0:
        raise ActionError(
            "app_not_running",
            "没有找到正在运行的网易云音乐，请先打开它。",
        )
    _focus_window(hwnd)
    time.sleep(0.3)
    _combo(VK_CONTROL, VK_F)
    time.sleep(0.5)
    _set_clipboard(song)
    _combo(VK_CONTROL, VK_V)
    time.sleep(0.2)
    _key(VK_RETURN)
    time.sleep(2.0)
    _key(VK_RETURN)
    time.sleep(0.5)
    _key(VK_MEDIA_PLAY_PAUSE)
    return {"query": song, "target": "netease_cloud_music"}
