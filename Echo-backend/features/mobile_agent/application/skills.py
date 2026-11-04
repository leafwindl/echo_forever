from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from features.mobile_agent.domain.entities import (
    MobileAgentActionError,
    MobileAgentCommandResult,
    MobileAgentDevice,
    MobileAgentError,
)
from features.mobile_agent.infrastructure.container import (
    get_mobile_agent_hub,
    get_mobile_agent_service,
)


class AppSkillError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SkillRunResult:
    skill: str
    device_id: str
    action: str
    data: dict[str, Any] = field(default_factory=dict)


class AppSkill(Protocol):
    name: str
    package: str
    actions: tuple[str, ...]

    async def run(
        self,
        runner: SkillRunner,
        action: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]: ...


class SkillRunner:
    def __init__(
        self,
        *,
        user_id: str,
        device: MobileAgentDevice,
        timeout_seconds: int = 25,
    ):
        self.user_id = user_id
        self.device = device
        self.timeout_seconds = timeout_seconds

    async def act(self, action: str, arguments: dict[str, Any] | None = None):
        return await get_mobile_agent_service().execute(
            user_id=self.user_id,
            device_id=self.device.device_id,
            action=action,
            arguments=arguments or {},
            timeout_seconds=self.timeout_seconds,
        )

    async def observe(self) -> dict[str, Any]:
        result = await self.act("observe")
        return result.data if isinstance(result, MobileAgentCommandResult) else {}

    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def wait_for_package(self, package: str, timeout_seconds: float = 6.0) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            snapshot = await self.observe()
            if str(snapshot.get("package") or "") == package:
                return True
            await self.wait(0.5)
        return False


_RESULT_LINE = re.compile(
    r"^\s*(?P<label>.+?)\s+\[(?P<x1>\d+),(?P<y1>\d+)\]"
    r"\[(?P<x2>\d+),(?P<y2>\d+)\]"
)


def _first_result_for_query(text: str, query: str) -> tuple[int, int] | None:
    candidates: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        match = _RESULT_LINE.match(line)
        if not match:
            continue
        label = match.group("label").strip()
        y1 = int(match.group("y1"))
        x1 = int(match.group("x1"))
        x2 = int(match.group("x2"))
        y2 = int(match.group("y2"))
        if y1 < 300 or not label or query not in label:
            continue
        if any(word in label for word in ("搜索", "搜索历史", "单曲", "综合", "评论")):
            continue
        candidates.append(((x1 + x2) // 2, (y1 + y2) // 2, y1))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[2])
    return candidates[0][0], candidates[0][1]


class NetEaseMusicSkill:
    name = "netmusic"
    package = "com.netease.cloudmusic"
    actions = ("play",)

    async def run(
        self,
        runner: SkillRunner,
        action: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if action != "play":
            raise AppSkillError("unsupported_skill_action", f"不支持：{action}")
        query = str(parameters.get("query") or "").strip()
        if not query or len(query) > 100:
            raise AppSkillError("invalid_query", "歌曲/歌手关键词不能为空")

        await runner.act("open_uri", {"uri": "orpheus://search"})
        if not await runner.wait_for_package(self.package, 6.0):
            raise AppSkillError("app_not_foreground", "网易云音乐没有回到前台")
        await runner.wait(0.5)
        await runner.act("action", {"kind": "tap", "x": 600, "y": 164})
        await runner.wait(0.3)
        await runner.act("action", {"kind": "text", "text": query})
        await runner.wait(0.8)
        await runner.act("action", {"kind": "tap", "x": 953, "y": 164})
        await runner.wait(2.0)
        with contextlib.suppress(MobileAgentError):
            await runner.act("action", {"kind": "tap_text", "text": "单曲"})
        await runner.wait(1.2)
        observed = await runner.observe()
        text = str(observed.get("text") or "")
        point = _first_result_for_query(text, query)
        if point is None:
            try:
                await runner.act("action", {"kind": "tap_text", "text": "单曲"})
                await runner.wait(1.0)
                observed = await runner.observe()
                text = str(observed.get("text") or "")
                point = _first_result_for_query(text, query)
            except MobileAgentError:
                point = None
        if point is None:
            raise AppSkillError(
                "song_not_found",
                f"没有在搜索结果里找到包含“{query}”的歌曲",
            )
        await runner.act(
            "action",
            {"kind": "tap", "x": point[0], "y": point[1]},
        )
        await runner.wait(2.0)
        after = await runner.observe()
        after_text = str(after.get("text") or "")
        playing = "播放暂停" in after_text or "正在播放" in after_text
        if not playing:
            await runner.act("action", {"kind": "tap", "x": 540, "y": 2060})
            await runner.wait(0.5)
            after = await runner.observe()
            after_text = str(after.get("text") or "")
            playing = "播放暂停" in after_text or "正在播放" in after_text
        return {
            "query": query,
            "package": self.package,
            "selected": point,
            "playing": playing,
            "observed": after_text[:3000],
        }


_SKILLS: dict[str, AppSkill] = {
    "netmusic": NetEaseMusicSkill(),
}


def _resolve_device(user_id: str, device_id: str) -> MobileAgentDevice:
    service = get_mobile_agent_service()
    hub = get_mobile_agent_hub()
    devices = service.list_devices(user_id)
    if not devices:
        raise MobileAgentActionError("no_paired_device", "还没有配对的手机")
    if device_id:
        device = next((d for d in devices if d.device_id == device_id), None)
        if device is None:
            raise MobileAgentActionError("device_not_found", "设备不存在")
        if not hub.is_online(device.device_id):
            raise MobileAgentActionError("device_offline", "手机当前不在线")
        return device
    device = next((d for d in devices if hub.is_online(d.device_id)), None)
    if device is None:
        raise MobileAgentActionError("device_offline", "没有在线的手机")
    return device


async def run_app_skill(
    *,
    user_id: str,
    skill: str,
    action: str,
    parameters: dict[str, Any],
    device_id: str = "",
) -> SkillRunResult:
    handler = _SKILLS.get(skill)
    if handler is None:
        raise AppSkillError("unknown_skill", f"未知 App Skill：{skill}")
    device = _resolve_device(user_id, device_id)
    runner = SkillRunner(user_id=user_id, device=device)
    try:
        data = await handler.run(runner, action, parameters)
    except MobileAgentError as exc:
        raise AppSkillError(exc.code, exc.message) from exc
    return SkillRunResult(
        skill=skill,
        device_id=device.device_id,
        action=action,
        data=data,
    )


__all__ = [
    "AppSkillError",
    "NetEaseMusicSkill",
    "SkillRunResult",
    "run_app_skill",
]
