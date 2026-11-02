from __future__ import annotations

import contextlib
import dataclasses
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from echo_desktop.client import CAPABILITIES, NodeRuntime, RuntimeCallbacks, pair_node
from echo_desktop.config import DesktopConfig, load_config, save_config
from echo_desktop.logging import log_path

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


class DesktopClientApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config_value: DesktopConfig | None = load_config()
        self.runtime: NodeRuntime | None = None
        self.events: queue.Queue[tuple] = queue.Queue()
        self.pair_frame_visible = self.config_value is None
        self._build_window()
        self._build_ui()
        self._drain_events()
        if self.config_value is not None:
            self._start_runtime()
        else:
            self._set_status("stopped", "还没有配对这台电脑")

    def _build_window(self) -> None:
        self.root.title("Echo Desktop")
        self.root.geometry("860x700")
        self.root.minsize(760, 560)
        with contextlib.suppress(tk.TclError):
            self.root.iconname("Echo Desktop")
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6b7a")
        style.configure("Warning.TLabel", foreground="#8a4b08")
        style.configure("TButton", font=("Microsoft YaHei UI", 10))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Echo Desktop", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Windows 电脑节点", style="Muted.TLabel").pack(
            side=tk.LEFT, padx=(12, 0), pady=(8, 0)
        )

        status_card = ttk.LabelFrame(outer, text="当前状态", padding=14)
        status_card.pack(fill=tk.X, pady=(16, 10))
        status_line = ttk.Frame(status_card)
        status_line.pack(fill=tk.X)
        self.status_dot = tk.Canvas(status_line, width=18, height=18, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self.status_dot_id = self.status_dot.create_oval(4, 4, 15, 15, fill="#718096", outline="")
        self.status_label = ttk.Label(status_line, text="未启动", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)
        self.detail_label = ttk.Label(status_line, text="", style="Muted.TLabel")
        self.detail_label.pack(side=tk.LEFT, padx=(12, 0))
        self.last_action_label = ttk.Label(
            status_card, text="最近操作：无", style="Muted.TLabel"
        )
        self.last_action_label.pack(fill=tk.X, pady=(8, 0))

        info = ttk.Frame(status_card)
        info.pack(fill=tk.X, pady=(10, 0))
        self.node_label = ttk.Label(info, text="", style="Muted.TLabel")
        self.node_label.pack(side=tk.LEFT)
        self.capability_label = ttk.Label(
            info,
            text="能力：" + " · ".join(CAPABILITIES),
            style="Muted.TLabel",
        )
        self.capability_label.pack(side=tk.RIGHT)
        self._refresh_node_label()

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(0, 10))
        self.start_button = ttk.Button(controls, text="启动连接", command=self._toggle_runtime)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="打开日志", command=self._open_log).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(controls, text="重新配对", command=self._toggle_pair_frame).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="退出", command=self._close).pack(side=tk.RIGHT)

        settings = ttk.LabelFrame(outer, text="权限与隐私", padding=12)
        settings.pack(fill=tk.X, pady=(0, 10))
        self.auto_approve_var = tk.BooleanVar(
            value=bool(self.config_value.auto_approve) if self.config_value else True
        )
        ttk.Checkbutton(
            settings,
            text="总是允许（不弹本机批准窗口）",
            variable=self.auto_approve_var,
            command=self._on_auto_approve_changed,
        ).pack(anchor=tk.W)
        ttk.Label(
            settings,
            text=(
                "开启后 Echo 可以在不询问的情况下打开应用、截图或看摄像头；"
                "每次操作仍会写入下面的日志和本地日志文件。"
            ),
            style="Warning.TLabel",
            wraplength=780,
        ).pack(anchor=tk.W, pady=(6, 0))

        self.pair_frame = ttk.LabelFrame(outer, text="配对这台电脑", padding=12)
        pair_row = ttk.Frame(self.pair_frame)
        pair_row.pack(fill=tk.X)
        ttk.Label(pair_row, text="服务器").pack(side=tk.LEFT)
        self.server_var = tk.StringVar(
            value=self.config_value.server_url if self.config_value else "https://api.echoaiforever.cn"
        )
        ttk.Entry(pair_row, textvariable=self.server_var, width=34).pack(
            side=tk.LEFT, padx=(8, 14)
        )
        ttk.Label(pair_row, text="电脑名").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(
            value=self.config_value.node_name if self.config_value else "我的电脑"
        )
        ttk.Entry(pair_row, textvariable=self.name_var, width=18).pack(
            side=tk.LEFT, padx=(8, 14)
        )
        code_row = ttk.Frame(self.pair_frame)
        code_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(code_row, text="配对码").pack(side=tk.LEFT)
        self.code_var = tk.StringVar()
        ttk.Entry(code_row, textvariable=self.code_var, width=12).pack(
            side=tk.LEFT, padx=(8, 14)
        )
        self.pair_button = ttk.Button(
            code_row, text="开始配对", command=self._pair_clicked
        )
        self.pair_button.pack(side=tk.LEFT)
        ttk.Label(
            code_row,
            text="配对码由服务端生成，默认 10 分钟内有效。",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))
        if self.pair_frame_visible:
            self.pair_frame.pack(fill=tk.X, pady=(0, 10))

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=14,
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
            self._toggle_pair_frame()
            return
        self._start_runtime()

    def _toggle_pair_frame(self) -> None:
        if self.pair_frame.winfo_ismapped():
            self.pair_frame.pack_forget()
        else:
            self.pair_frame.pack(fill=tk.X, pady=(0, 10), before=self.log_text.master)

    def _pair_clicked(self) -> None:
        server = self.server_var.get().strip()
        code = self.code_var.get().strip()
        name = self.name_var.get().strip() or "我的电脑"
        if not server or not code:
            messagebox.showwarning("配对", "请填写服务器地址和配对码。", parent=self.root)
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

    def _on_auto_approve_changed(self) -> None:
        if self.config_value is not None:
            self.config_value = dataclasses.replace(
                self.config_value,
                auto_approve=bool(self.auto_approve_var.get()),
            )
            save_config(self.config_value)
        if self.runtime is not None:
            self.runtime.auto_approve = bool(self.auto_approve_var.get())
        state = "开启" if self.auto_approve_var.get() else "关闭"
        self._append_log("INFO", f"本机批准窗口：{state}")

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
                    self.auto_approve_var.set(config.auto_approve)
                    self._refresh_node_label()
                    self.code_var.set("")
                    self.pair_button.configure(state=tk.NORMAL)
                    self._append_log("INFO", f"配对成功：{config.node_name}")
                    self._set_status("connecting", "配对完成，正在连接")
                    if self.pair_frame.winfo_ismapped():
                        self.pair_frame.pack_forget()
                    self._start_runtime()
                elif kind == "pair_failed":
                    self.pair_button.configure(state=tk.NORMAL)
                    self._append_log("ERROR", f"配对失败：{event[1]}")
                    self._set_status("error", "配对失败")
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def _open_log(self) -> None:
        try:
            os.startfile(log_path())
        except OSError as exc:
            messagebox.showerror("打开日志", f"无法打开日志：{exc}", parent=self.root)

    def _close(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DesktopClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
