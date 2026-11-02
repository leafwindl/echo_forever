from __future__ import annotations

import os
import subprocess
from pathlib import Path

from echo_desktop.protocol import ActionError

_DEFAULT_DSH = Path(r"D:\DeepSeek\resources\runtime\cli\bin\dsh.cmd")
_MAX_OUTPUT = 12_000


def _resolve_dsh() -> Path:
    configured = os.environ.get("ECHO_DESKTOP_DSH_COMMAND", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(_DEFAULT_DSH)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ActionError(
        "dsh_not_found",
        "没有找到 DSH 命令，请设置 ECHO_DESKTOP_DSH_COMMAND。",
    )


def run_dsh_task(instruction: str, workspace: str = "") -> dict:
    task = " ".join(str(instruction or "").split()).strip()
    if not task:
        raise ActionError("invalid_instruction", "DSH 任务不能为空。")
    target = Path(workspace).expanduser() if workspace.strip() else Path.home()
    if not target.is_dir():
        raise ActionError("workspace_not_found", f"工作目录不存在：{target}")
    dsh = _resolve_dsh()
    command = [str(dsh), "headless", task]
    if os.name == "nt" and dsh.suffix.lower() in {".cmd", ".bat"}:
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/q", "/c", *command]
    try:
        completed = subprocess.run(
            command,
            cwd=str(target),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ActionError("dsh_timeout", "DSH 任务超过 5 分钟还没结束。") from exc
    except OSError as exc:
        raise ActionError("dsh_launch_failed", f"启动 DSH 失败：{exc}") from exc
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0 and not stdout:
        raise ActionError(
            "dsh_failed",
            f"DSH 任务失败（退出码 {completed.returncode}）：{stderr[-800:]}",
        )
    return {
        "exit_code": completed.returncode,
        "workspace": str(target),
        "result": stdout[-_MAX_OUTPUT:],
        "stderr": stderr[-2000:],
    }
