"""本地聊天 demo：验证人设与提示词效果。

用法：
    python scripts/chat_demo.py

默认连本地后端 http://127.0.0.1:8000，测试账号 19900000001（本地验证码 123456）。
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
import uuid
from tkinter import ttk

import httpx


class ChatDemo:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Echo 语气测试")
        self.root.geometry("760x680")
        self.client = httpx.Client(timeout=120.0)
        self.token = ""
        self.device_id = str(uuid.uuid4())
        self.last_message_id = 0
        self.polling = False
        self._build()
        self._connect()

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)
        ttk.Label(top, text="服务器").pack(side=tk.LEFT)
        self.server_var = tk.StringVar(value="http://127.0.0.1:8000")
        ttk.Entry(top, textvariable=self.server_var, width=26).pack(side=tk.LEFT, padx=6)
        ttk.Label(top, text="手机号").pack(side=tk.LEFT)
        self.phone_var = tk.StringVar(value="19900000001")
        ttk.Entry(top, textvariable=self.phone_var, width=14).pack(side=tk.LEFT, padx=6)
        ttk.Label(top, text="验证码").pack(side=tk.LEFT)
        self.code_var = tk.StringVar(value="123456")
        ttk.Entry(top, textvariable=self.code_var, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="重新连接", command=self._connect).pack(side=tk.LEFT, padx=6)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 0)).pack(fill=tk.X)

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        self.chat = tk.Text(
            body,
            state=tk.DISABLED,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 11),
            background="#fbfcfe",
            relief=tk.FLAT,
        )
        scroll = ttk.Scrollbar(body, command=self.chat.yview)
        self.chat.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat.pack(fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill=tk.X)
        self.entry = ttk.Entry(bottom, font=("Microsoft YaHei UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _event: self._send())
        ttk.Button(bottom, text="发送", command=self._send).pack(side=tk.LEFT, padx=8)
        ttk.Button(bottom, text="清屏", command=self._clear).pack(side=tk.LEFT)

    def _append(self, role: str, text: str) -> None:
        prefix = "你" if role == "user" else "Echo"
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{prefix}：{text}\n")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _clear(self) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _connect(self) -> None:
        self.polling = False
        threading.Thread(target=self._login, daemon=True).start()

    def _login(self) -> None:
        try:
            server = self.server_var.get().strip().rstrip("/")
            phone = self.phone_var.get().strip()
            code = self.code_var.get().strip()
            challenge = self.client.post(
                f"{server}/login/phone",
                json={"phone": phone, "device_id": self.device_id, "purpose": "login"},
            )
            challenge.raise_for_status()
            verify = self.client.post(
                f"{server}/login/verify",
                json={
                    "request_id": challenge.json()["request_id"],
                    "phone": phone,
                    "code": code,
                    "device_id": self.device_id,
                },
            )
            verify.raise_for_status()
            self.token = verify.json()["access_token"]
            page = self.client.get(
                f"{server}/chat/messages",
                headers=self._headers(),
                params={"limit": 1},
            ).json()
            self.last_message_id = max(
                (item["message_id"] for item in page.get("items", [])),
                default=0,
            )
            self.status_var.set(f"已连接 {phone}，输入消息开始测试")
            if not self.polling:
                self.polling = True
                threading.Thread(target=self._poll_loop, daemon=True).start()
        except Exception as exc:
            self.status_var.set(f"连接失败：{exc}")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _poll_loop(self) -> None:
        while self.polling:
            try:
                server = self.server_var.get().strip().rstrip("/")
                page = self.client.get(
                    f"{server}/chat/messages",
                    headers=self._headers(),
                    params={"limit": 30},
                ).json()
                items = sorted(page.get("items", []), key=lambda item: item["message_id"])
                for item in items:
                    if item["message_id"] <= self.last_message_id:
                        continue
                    self.last_message_id = item["message_id"]
                    content = (item.get("content") or "").strip()
                    if content:
                        self.root.after(0, self._append, item["role"], content)
            except Exception:
                pass
            time.sleep(1.2)

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text or not self.token:
            return
        self.entry.delete(0, tk.END)
        self._append("user", text)

        def worker() -> None:
            try:
                server = self.server_var.get().strip().rstrip("/")
                self.client.post(
                    f"{server}/chat/messages",
                    headers=self._headers(),
                    json={
                        "client_message_id": str(uuid.uuid4()),
                        "message_type": "text",
                        "text": text,
                    },
                )
            except Exception as exc:
                self.root.after(0, self.status_var.set, f"发送失败：{exc}")

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    ChatDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
