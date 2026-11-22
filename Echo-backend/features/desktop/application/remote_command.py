"""电脑节点的异步 exec：提交 job 后轮询 job_result，统一等待与状态判定。

agent 的 exec 有两种返回形态：旧版同步返回 output，新版先返回 job_id 再查询。
多个 feature 都需要同一套等待逻辑，判定词汇必须只有一份，否则就会出现
「一方等 done、另一方等 completed」这种永远等不到结果的轮询。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from features.desktop.application.desktop_service import DesktopService
from features.desktop.domain.entities import (
    DesktopError,
    DesktopOfflineError,
    DesktopTimeoutError,
)

logger = logging.getLogger(__name__)

# agent 的完成态。done 是当前协议；completed 是历史写法，保留兼容。
DONE_STATUSES = frozenset({"done", "completed"})
# 终态失败。missing 表示 agent 已经丢失该 job，继续轮询没有意义。
FAILED_STATUSES = frozenset({"failed", "missing", "canceled", "cancelled"})

# 单次 job_result 查询连续超时到这个次数就放弃，避免 agent 卡死时白等
POLL_MAX_CONSECUTIVE_TIMEOUTS = 3


@dataclass(frozen=True)
class RemoteCommandResult:
    ok: bool
    output: str
    exit_code: int | None = None
    status: str = ""
    job_id: Any = None


def _status_of(data: dict[str, Any]) -> str:
    return str(data.get("status") or "").strip().lower()


def _text_of(data: dict[str, Any]) -> str:
    for key in ("output", "error", "message"):
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _exit_code_of(data: dict[str, Any]) -> int | None:
    value = data.get("exit_code")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def run_remote_command(
    service: DesktopService,
    *,
    user_id: str,
    command: str,
    owner_type: str = "echo",
    timeout_seconds: int = 120,
    submit_timeout_seconds: int = 30,
    poll_interval_seconds: float = 2.0,
    poll_timeout_seconds: int = 20,
) -> RemoteCommandResult:
    """在电脑节点执行命令并等待结果。

    timeout_seconds 是整个等待的上限，不是单次请求的上限。
    """
    try:
        start = await service.execute(
            user_id=user_id,
            action="exec",
            arguments={"command": command},
            timeout_seconds=submit_timeout_seconds,
            owner_type=owner_type,
        )
    except DesktopOfflineError as exc:
        return RemoteCommandResult(False, exc.message, status=exc.code)
    except DesktopTimeoutError as exc:
        return RemoteCommandResult(False, exc.message, status=exc.code)
    except DesktopError as exc:
        return RemoteCommandResult(False, exc.message, status=exc.code)

    job_id = start.data.get("job_id")
    if job_id is None:
        # 旧版 agent 同步返回输出，没有 job 可轮询
        return RemoteCommandResult(
            True,
            _text_of(start.data).strip(),
            exit_code=_exit_code_of(start.data),
            status="sync",
        )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    consecutive_timeouts = 0
    logged_unknown_status = False
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval_seconds, remaining))
        if loop.time() >= deadline:
            break
        try:
            result = await service.execute(
                user_id=user_id,
                action="job_result",
                arguments={"job_id": job_id},
                timeout_seconds=poll_timeout_seconds,
                owner_type=owner_type,
            )
        except DesktopOfflineError as exc:
            return RemoteCommandResult(False, exc.message, status=exc.code, job_id=job_id)
        except DesktopTimeoutError:
            # 单次查询超时通常只是 agent 忙，等它一会儿再说
            consecutive_timeouts += 1
            if consecutive_timeouts >= POLL_MAX_CONSECUTIVE_TIMEOUTS:
                logger.warning(
                    "desktop job_result 连续超时 user_id=%s job_id=%s",
                    user_id,
                    job_id,
                )
                return RemoteCommandResult(
                    False,
                    "查询任务结果连续超时。",
                    status="poll_timeout",
                    job_id=job_id,
                )
            continue
        except DesktopError as exc:
            return RemoteCommandResult(False, exc.message, status=exc.code, job_id=job_id)
        consecutive_timeouts = 0

        status = _status_of(result.data)
        if status in DONE_STATUSES:
            return RemoteCommandResult(
                True,
                _text_of(result.data).strip(),
                exit_code=_exit_code_of(result.data),
                status=status,
                job_id=job_id,
            )
        if status in FAILED_STATUSES:
            return RemoteCommandResult(
                False,
                _text_of(result.data).strip() or status,
                exit_code=_exit_code_of(result.data),
                status=status,
                job_id=job_id,
            )
        if not status and not logged_unknown_status:
            # 协议对不上时这里能直接看出 agent 到底回了什么
            logger.warning(
                "desktop job_result 缺少 status user_id=%s job_id=%s keys=%s",
                user_id,
                job_id,
                sorted(result.data),
            )
            logged_unknown_status = True

    return RemoteCommandResult(
        False,
        "命令执行超过时限仍未完成。",
        status="timeout",
        job_id=job_id,
    )


__all__ = ["DONE_STATUSES", "FAILED_STATUSES", "RemoteCommandResult", "run_remote_command"]
