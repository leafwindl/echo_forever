from __future__ import annotations

import contextlib
import dataclasses
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

from echo_desktop import autostart
from echo_desktop.client import CAPABILITIES, NodeRuntime, RuntimeCallbacks, pair_node
from echo_desktop.config import DesktopConfig, load_config, save_config
from echo_desktop.logging import log_path
from echo_desktop.tray import TrayController

_STATUS_TEXT = {
    "starting": "启动中",
    "connecting": "正在连接",
    "online": "在线",
    "stopped": "已停止",
    "auth_error": "配对失效",
    "error": "出错",
}
_STATUS_COLOR = {
    "starting": "#8a6d3b",
    "connecting": "#b7791f",
    "online": "#2f855a",
    "stopped": "#718096",
    "auth_error": "#c53030",
    "error": "#c53030",
}
_DEFAULT_SERVER = "https://api.echoaiforever.cn"
_DEFAULT_TTS = "http://127.0.0.1:18080"


def _validate_server(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        raise ValueError("服务器地址不能为空")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("服务器地址必须是 http(s)://主机 形式")
    return candidate


def _validate_tts(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("语音服务地址必须是 http(s)://主机 形式")
    return candidate


class DesktopClientApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config_value: DesktopConfig | None = load_config()
        self.runtime: NodeRuntime | None = None
        self.events: queue.Queue[tuple] = queue.Queue()
        self.tray: TrayController | None = None
        self._build_window()
        self._build_ui()
        self._load_settings_into_form()
        self._drain_events()
        self._init_tray()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_button)
        self.root.bind("<Unmap>", self._on_unmap)
        if self.config_value is not None:
            self._start_runtime()
        else:
            self._set_status("stopped", "还没有配对这台电脑")

    # ---------- 窗口与布局 ----------

    def _build_window(self) -> None:
        self.root.title("Echo Desktop")
        self.root.geometry("920x740")
        self.root.minsize(820, 620)
        with contextlib.suppress(tk.TclError):
            self.root.iconname("Echo Desktop")
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6b7a")
        style.configure("Warning.TLabel", foreground="#8a4b08")
        style.configure("TButton", font=("Microsoft YaHei UI", 10))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Echo Desktop", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Windows 电脑节点", style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 0), pady=(8, 0)
        )
        self.connection_badge = ttk.Label(header, text="", style="Muted.TLabel")
        self.connection_badge.pack(side=tk.RIGHT, pady=(8, 0))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.status_tab = ttk.Frame(notebook, padding=12)
        self.settings_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.status_tab, text="运行状态")
        notebook.add(self.settings_tab, text="设置")

        self._build_status_tab(self.status_tab)
        self._build_settings_tab(self.settings_tab)

    def _build_status_tab(self, parent: ttk.Frame) -> None:
        status_card = ttk.LabelFrame(parent, text="当前状态", padding=14)
        status_card.pack(fill=tk.X)

        status_line = ttk.Frame(status_card)
        status_line.pack(fill=tk.X)
        self.status_dot = tk.Canvas(status_line, width=18, height=18, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self.status_dot_id = self.status_dot.create_oval(4, 4, 15, 15, fill="#718096", outline="")
        self.status_label = ttk.Label(status_line, text="未启动", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)
        self.detail_label = ttk.Label(status_line, text="", style="Muted.TLabel")
        self.detail_label.pack(side=tk.LEFT, padx=(12, 0))

        self.last_action_label = ttk.Label(status_card, text="最近操作：无", style="Muted.TLabel")
        self.last_action_label.pack(fill=tk.X, pady=(8, 0))

        info = ttk.Frame(status_card)
        info.pack(fill=tk.X, pady=(10, 0))
        self.node_label = ttk.Label(info, text="", style="Muted.TLabel")
        self.node_label.pack(side=tk.LEFT)
        ttk.Label(
            info,
            text="能力：" + " · ".join(CAPABILITIES),
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(12, 8))
        self.start_button = ttk.Button(controls, text="启动连接", command=self._toggle_runtime)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="打开日志文件", command=self._open_log).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(controls, text="设置", command=self._show_settings).pack(side=tk.LEFT)
        ttk.Button(controls, text="退出", command=self._on_close_button).pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(parent, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=16,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
            background="#fbfcfe",
            relief=tk.FLAT,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._append_log("INFO", "客户端已启动")

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        connection = ttk.LabelFrame(parent, text="连接", padding=12)
        connection.pack(fill=tk.X)

        row = ttk.Frame(connection)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="服务器地址", width=12).pack(side=tk.LEFT)
        self.server_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.server_var, width=42).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row, text="例如 https://api.echoaiforever.cn", style="Muted.TLabel").pack(
            side=tk.LEFT
        )

        row = ttk.Frame(connection)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="电脑名称", width=12).pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.name_var, width=24).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row, text="显示在 App 里的电脑名", style="Muted.TLabel").pack(side=tk.LEFT)

        row = ttk.Frame(connection)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="语音服务", width=12).pack(side=tk.LEFT)
        self.tts_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.tts_var, width=42).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row, text="本机 TTS 地址，留空则不启用", style="Muted.TLabel").pack(side=tk.LEFT)

        privacy = ttk.LabelFrame(parent, text="权限与隐私", padding=12)
        privacy.pack(fill=tk.X, pady=(12, 0))
        self.auto_approve_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            privacy,
            text="总是允许（不弹本机批准窗口）",
            variable=self.auto_approve_var,
        ).pack(anchor=tk.W)
        ttk.Label(
            privacy,
            text=(
                "开启后 Echo 可以在不询问的情况下打开应用、截图或看摄像头；"
                "每次操作仍会写入运行日志和本地日志文件。"
            ),
            style="Warning.TLabel",
            wraplength=780,
        ).pack(anchor=tk.W, pady=(6, 0))

        startup = ttk.LabelFrame(parent, text="开机自启动", padding=12)
        startup.pack(fill=tk.X, pady=(12, 0))
        self.autostart_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            startup,
            text="登录 Windows 后自动打开 Echo Desktop 并连接",
            variable=self.autostart_var,
            command=self._on_autostart_changed,
        ).pack(anchor=tk.W)
        ttk.Label(
            startup,
            text="关闭时不会修改系统设置；开启后写入当前用户启动项，可随时取消。",
            style="Muted.TLabel",
            wraplength=780,
        ).pack(anchor=tk.W, pady=(6, 0))

        pair = ttk.LabelFrame(parent, text="配对新电脑", padding=12)
        pair.pack(fill=tk.X, pady=(12, 0))
        pair_row = ttk.Frame(pair)
        pair_row.pack(fill=tk.X)
        ttk.Label(pair_row, text="配对码").pack(side=tk.LEFT)
        self.code_var = tk.StringVar()
        ttk.Entry(pair_row, textvariable=self.code_var, width=14).pack(
            side=tk.LEFT, padx=(8, 12)
        )
        self.pair_button = ttk.Button(pair_row, text="开始配对", command=self._pair_clicked)
        self.pair_button.pack(side=tk.LEFT)
        ttk.Label(
            pair_row,
            text="配对码由服务端生成，默认 10 分钟内有效。",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(16, 0))
        self.save_button = ttk.Button(actions, text="保存设置", command=self._save_settings)
        self.save_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="重新连接", command=self._reconnect).pack(side=tk.LEFT, padx=8)
        self.settings_hint = ttk.Label(actions, text="", style="Muted.TLabel")
        self.settings_hint.pack(side=tk.LEFT, padx=(12, 0))

    # ---------- 配置 ----------

    def _load_settings_into_form(self) -> None:
        config = self.config_value
        self.server_var.set(config.server_url if config else _DEFAULT_SERVER)
        self.name_var.set(config.node_name if config else "我的电脑")
        self.tts_var.set(config.tts_url if config else _DEFAULT_TTS)
        self.auto_approve_var.set(bool(config.auto_approve) if config else True)
        self.autostart_var.set(autostart.is_autostart_enabled())
        self._refresh_node_label()
        self._refresh_connection_badge()

    def _refresh_connection_badge(self) -> None:
        if self.config_value is None:
            self.connection_badge.configure(text="未配对")
            return
        self.connection_badge.configure(text=self.config_value.server_url)

    def _save_settings(self) -> None:
        try:
            server = _validate_server(self.server_var.get())
            tts = _validate_tts(self.tts_var.get())
        except ValueError as exc:
            self._set_settings_hint(str(exc), error=True)
            return

        name = self.name_var.get().strip() or "我的电脑"
        if self.config_value is None:
            self._set_settings_hint("还没有配对，请先填写配对码完成配对。", error=True)
            return

        previous = self.config_value
        updated = dataclasses.replace(
            previous,
            server_url=server,
            node_name=name,
            tts_url=tts,
            auto_approve=bool(self.auto_approve_var.get()),
        )
        save_config(updated)
        self.config_value = updated
        self._refresh_node_label()
        self._refresh_connection_badge()
        self._set_settings_hint("已保存")
        self._append_log("INFO", "设置已保存")

        if self.runtime is not None:
            self.runtime.auto_approve = updated.auto_approve
        if previous.server_url != server or previous.node_name != name:
            self._append_log("INFO", "服务器或电脑名已变化，正在重新连接")
            self._start_runtime()

    def _reconnect(self) -> None:
        if self.config_value is None:
            self._set_settings_hint("还没有配对", error=True)
            return
        self._start_runtime()
        self._set_settings_hint("已重新连接")

    def _set_settings_hint(self, text: str, *, error: bool = False) -> None:
        self.settings_hint.configure(text=text, foreground="#c53030" if error else "#2f855a")

    def _show_settings(self) -> None:
        for index, tab in enumerate(self.status_tab.master.tabs()):
            if self.status_tab.master.nametowidget(tab) is self.settings_tab:
                self.status_tab.master.select(index)
                return

    # ---------- 开机自启 ----------

    def _on_autostart_changed(self) -> None:
        enabled = bool(self.autostart_var.get())
        try:
            autostart.set_autostart(enabled)
        except OSError as exc:
            self.autostart_var.set(not enabled)
            messagebox.showerror("开机自启动", f"设置失败：{exc}", parent=self.root)
            return
        self._append_log("INFO", f"开机自启动：{'开启' if enabled else '关闭'}")
        self._set_settings_hint("开机自启动已开启" if enabled else "开机自启动已关闭")
        self._refresh_tray()

    # ---------- 运行时 ----------

    def _callbacks(self) -> RuntimeCallbacks:
        return RuntimeCallbacks(
            on_status=lambda status, detail: self.events.put(("status", status, detail)),
            on_log=lambda level, message: self.events.put(("log", level, message)),
            on_action=lambda action, state, detail: self.events.put(
                ("action", action, state, detail)
            ),
        )

    def _start_runtime(self) -> None:
        if self.config_value is None:
            return
        if self.runtime is not None:
            self.runtime.stop()
        self.runtime = NodeRuntime(self.config_value, callbacks=self._callbacks())
        self.runtime.start()
        self.start_button.configure(text="停止连接")
        self._append_log("INFO", "正在启动连接")

    def _toggle_runtime(self) -> None:
        if self.runtime is not None and self.runtime.running:
            self.runtime.stop()
            self.start_button.configure(text="启动连接")
            return
        if self.config_value is None:
            self._show_settings()
            return
        self._start_runtime()

    # ---------- 配对 ----------

    def _pair_clicked(self) -> None:
        try:
            server = _validate_server(self.server_var.get())
        except ValueError as exc:
            messagebox.showwarning("配对", str(exc), parent=self.root)
            return
        code = self.code_var.get().strip()
        name = self.name_var.get().strip() or "我的电脑"
        if not code:
            messagebox.showwarning("配对", "请填写配对码。", parent=self.root)
            return
        self.pair_button.configure(state=tk.DISABLED)
        self._append_log("INFO", "正在配对这台电脑")
        threading.Thread(
            target=self._pair_worker,
            args=(server, code, name),
            daemon=True,
        ).start()

    def _pair_worker(self, server: str, code: str, name: str) -> None:
        try:
            config = pair_node(server_url=server, code=code, node_name=name)
        except Exception as exc:
            self.events.put(("pair_failed", str(exc)))
            return
        self.events.put(("paired", config))

    # ---------- 状态与日志 ----------

    def _refresh_node_label(self) -> None:
        if self.config_value is None:
            self.node_label.configure(text="未配对")
            return
        self.node_label.configure(
            text=f"{self.config_value.node_name} · {self.config_value.node_id}"
        )

    def _set_status(self, status: str, detail: str) -> None:
        color = _STATUS_COLOR.get(status, "#718096")
        text = _STATUS_TEXT.get(status, status)
        self.status_dot.itemconfigure(self.status_dot_id, fill=color)
        self.status_label.configure(text=text)
        self.detail_label.configure(text=detail)

    def _append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{timestamp}  {level:<5}  {message}\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 1200:
            self.log_text.delete("1.0", "200.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self._set_status(event[1], event[2])
                    self._refresh_tray()
                elif kind == "log":
                    self._append_log(event[1], event[2])
                elif kind == "action":
                    action, state, detail = event[1], event[2], event[3]
                    suffix = f" ({detail})" if detail else ""
                    self.last_action_label.configure(
                        text=f"最近操作：{action} · {state}{suffix}"
                    )
                elif kind == "paired":
                    config = event[1]
                    self.config_value = config
                    save_config(config)
                    self.server_var.set(config.server_url)
                    self.name_var.set(config.node_name)
                    self.auto_approve_var.set(config.auto_approve)
                    self._refresh_node_label()
                    self._refresh_connection_badge()
                    self.code_var.set("")
                    self.pair_button.configure(state=tk.NORMAL)
                    self._append_log("INFO", f"配对成功：{config.node_name}")
                    self._set_settings_hint("配对成功")
                    self._set_status("connecting", "配对完成，正在连接")
                    self._start_runtime()
                elif kind == "pair_failed":
                    self.pair_button.configure(state=tk.NORMAL)
                    self._append_log("ERROR", f"配对失败：{event[1]}")
                    self._set_settings_hint(f"配对失败：{event[1]}", error=True)
                    self._set_status("error", "配对失败")
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def _open_log(self) -> None:
        try:
            os.startfile(log_path())
        except OSError as exc:
            messagebox.showerror("打开日志", f"无法打开日志：{exc}", parent=self.root)

    def _init_tray(self) -> None:
        try:
            self.tray = TrayController(
                root=self.root,
                on_show=self._show_window,
                on_hide=self._hide_to_tray,
                on_toggle_connection=self._toggle_runtime,
                on_toggle_autostart=self._toggle_tray_autostart,
                is_running=lambda: self.runtime is not None and self.runtime.running,
                is_autostart=autostart.is_autostart_enabled,
                on_quit=self._quit,
            )
            self.tray.start()
        except Exception:
            self.tray = None
            self._append_log("WARN ", "系统托盘不可用，关闭窗口将直接退出")

    def _refresh_tray(self) -> None:
        if self.tray is not None:
            self.tray.refresh()

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()
        self._append_log("INFO", "窗口已最小化到托盘")

    def _on_unmap(self, event) -> None:
        if event.widget is not self.root or self.tray is None:
            return
        if self.root.state() == "iconic":
            self.root.withdraw()
            self._append_log("INFO", "窗口已最小化到托盘")

    def _on_close_button(self) -> None:
        if self.tray is not None:
            self._hide_to_tray()
            return
        self._quit()

    def _toggle_tray_autostart(self) -> None:
        enabled = not autostart.is_autostart_enabled()
        try:
            autostart.set_autostart(enabled)
        except OSError as exc:
            self._append_log("ERROR", f"开机自启动设置失败：{exc}")
            return
        self.autostart_var.set(enabled)
        self._append_log("INFO", f"开机自启动：{'开启' if enabled else '关闭'}")
        self._refresh_tray()

    def _quit(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DesktopClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
