from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_ICON_RELATIVE = (
    Path("app")
    / "android"
    / "app"
    / "src"
    / "main"
    / "res"
    / "mipmap-xxxhdpi"
    / "ic_launcher.png"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _fallback_image() -> Image.Image:
    """没有 App 图标时画一个蓝色鲸鱼剪影。"""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 61, 61), fill=(38, 96, 168, 255))
    draw.ellipse((15, 27, 45, 45), fill=(255, 255, 255, 240))
    draw.polygon([(43, 34), (59, 23), (55, 39)], fill=(255, 255, 255, 240))
    draw.ellipse((19, 32, 24, 37), fill=(38, 96, 168, 255))
    return image


def _load_image() -> Image.Image:
    try:
        path = _repo_root() / _ICON_RELATIVE
        image = Image.open(path).convert("RGBA")
        return image.resize((64, 64), Image.LANCZOS)
    except Exception:
        logger.debug("tray icon fallback", exc_info=True)
        return _fallback_image()


class TrayController:
    """系统托盘：显示/隐藏窗口、启停连接、开机自启、退出。"""

    def __init__(
        self,
        *,
        root,
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_toggle_connection: Callable[[], None],
        on_toggle_autostart: Callable[[], None],
        is_running: Callable[[], bool],
        is_autostart: Callable[[], bool],
        on_quit: Callable[[], None],
    ):
        self.root = root
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_toggle_connection = on_toggle_connection
        self._on_toggle_autostart = on_toggle_autostart
        self._is_running = is_running
        self._is_autostart = is_autostart
        self._on_quit = on_quit
        self.icon = pystray.Icon(
            "echo-desktop",
            _load_image(),
            "Echo Desktop",
            self._build_menu(),
        )

    # 托盘回调在 pystray 线程，统一调度回 tkinter 主线程
    def _dispatch(self, callback: Callable[[], None]) -> None:
        try:
            self.root.after(0, callback)
        except Exception:
            logger.debug("tray dispatch failed", exc_info=True)

    def _build_menu(self) -> pystray.Menu:
        running = self._is_running()
        return pystray.Menu(
            pystray.MenuItem(
                "显示窗口",
                lambda: self._dispatch(self._on_show),
                default=True,
            ),
            pystray.MenuItem("隐藏到托盘", lambda: self._dispatch(self._on_hide)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "停止连接" if running else "启动连接",
                lambda: self._dispatch(self._on_toggle_connection),
            ),
            pystray.MenuItem(
                "开机自启动",
                lambda: self._dispatch(self._on_toggle_autostart),
                checked=lambda item: self._is_autostart(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出 Echo Desktop", lambda: self._dispatch(self._on_quit)),
        )

    def refresh(self) -> None:
        try:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception:
            logger.debug("tray refresh failed", exc_info=True)

    def notify(self, title: str, message: str) -> None:
        try:
            self.icon.notify(message, title)
        except Exception:
            logger.debug("tray notify failed", exc_info=True)

    def start(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            logger.debug("tray stop failed", exc_info=True)
