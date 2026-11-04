from __future__ import annotations

import json
from typing import Any

from providers.llm_provider import get_llm_provider
from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.mobile_agent.application.skills import AppSkillError, run_app_skill
from features.mobile_agent.domain.entities import MobileAgentError
from features.mobile_agent.public import (
    execute_mobile_agent_action,
    list_mobile_agent_devices,
)


class PhoneStatusArguments(BaseModel):
    pass


class PhoneObserveArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)
    include_screenshot: bool = False


class PhoneScreenshotArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)


class PhoneScreenOcrArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)


class PhoneLaunchAppArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)
    package: str = Field(min_length=1, max_length=200)


class PhoneActionArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)
    kind: str = Field(
        description="tap / tap_text / text / back / home / recents",
        max_length=32,
    )
    x: int = Field(default=0, ge=0, le=10000)
    y: int = Field(default=0, ge=0, le=10000)
    text: str = Field(default="", max_length=2000)


class PhoneNotificationsArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)


class PhonePlayMusicArguments(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    device_id: str = Field(default="", max_length=100)


class PhoneWechatSendArguments(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    device_id: str = Field(default="", max_length=100)


class PhoneXiaohongshuArguments(BaseModel):
    action: str = Field(default="feed", pattern="^(feed|search|open|comments)$")
    query: str = Field(default="", max_length=100)
    count: int = Field(default=2, ge=1, le=10)
    device_id: str = Field(default="", max_length=100)


class PhoneDouyinArguments(BaseModel):
    action: str = Field(default="feed", pattern="^(feed|search|play|comments)$")
    query: str = Field(default="", max_length=100)
    count: int = Field(default=3, ge=1, le=10)
    device_id: str = Field(default="", max_length=100)


class PhoneBilibiliArguments(BaseModel):
    action: str = Field(default="play", pattern="^(play|comments)$")
    query: str = Field(min_length=1, max_length=100)
    device_id: str = Field(default="", max_length=100)


class PhoneRunTaskArguments(BaseModel):
    task: str = Field(min_length=1, max_length=1000)
    device_id: str = Field(default="", max_length=100)
    max_steps: int = Field(default=8, ge=1, le=20)


class PhoneStopArguments(BaseModel):
    device_id: str = Field(default="", max_length=100)


def _failed(tool_name: str, code: str, message: str) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.FAILED,
        error_code=code,
        safe_for_model=message,
    )


def _completed(
    tool_name: str, *, safe_for_model: str, data: dict[str, Any] | None = None
) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.COMPLETED,
        data=data or {},
        safe_for_model=safe_for_model,
    )


def _online_device(user_id: str, device_id: str):
    devices = list_mobile_agent_devices(user_id)
    online = [item for item in devices if item.online]
    if device_id:
        for item in online:
            if item.device.device_id == device_id:
                return item.device
        return None
    return online[0].device if online else None


def _register(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    arguments_model: type[BaseModel],
    handler,
    risk: ToolRisk,
    timeout_seconds: int,
    max_calls: int = 2,
) -> None:
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name=name,
                description=description,
                risk_level=risk,
                timeout_seconds=timeout_seconds,
                allowed_modes=("chat",),
                max_calls_per_turn=max_calls,
                max_successful_calls_per_turn=max_calls,
                allow_proactive=False,
            ),
            arguments_model=arguments_model,
            handler=handler,
        )
    )


async def _execute(
    *,
    context: ToolExecutionContext,
    device,
    action: str,
    arguments: dict[str, Any],
    timeout_seconds: int = 25,
) -> dict[str, Any]:
    result = await execute_mobile_agent_action(
        user_id=context.user_id,
        device_id=device.device_id,
        action=action,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
    )
    return result.data


def register_mobile_agent_tools(registry: ToolRegistry) -> None:
    async def status_handler(context: ToolExecutionContext, arguments: BaseModel):
        PhoneStatusArguments.model_validate(arguments)
        devices = list_mobile_agent_devices(context.user_id)
        if not devices:
            return _completed(
                "phone_status",
                safe_for_model="还没有配对手机 Agent。",
                data={"devices": []},
            )
        lines = [
            f"{item.device.name}（{item.device.device_id}）："
            f"{'在线' if item.online else '离线'}"
            for item in devices
        ]
        return _completed(
            "phone_status",
            safe_for_model="手机 Agent：\n" + "\n".join(lines),
            data={
                "devices": [
                    {
                        "device_id": item.device.device_id,
                        "name": item.device.name,
                        "online": item.online,
                    }
                    for item in devices
                ]
            },
        )

    async def observe_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneObserveArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_observe", "phone_offline", "手机 Agent 当前不在线")
        try:
            data = await _execute(
                context=context,
                device=device,
                action="observe",
                arguments={},
            )
        except MobileAgentError as exc:
            return _failed("phone_observe", exc.code, exc.message)
        if parsed.include_screenshot:
            try:
                shot = await _execute(
                    context=context,
                    device=device,
                    action="screenshot",
                    arguments={},
                )
                data["screenshot_base64"] = shot.get("image_base64", "")
            except MobileAgentError:
                data["screenshot_base64"] = ""
        text = str(data.get("text") or "")[:6000]
        return _completed(
            "phone_observe",
            safe_for_model=f"手机当前界面：\n{text}",
            data=data,
        )

    async def screenshot_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneScreenshotArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_screenshot", "phone_offline", "手机 Agent 当前不在线")
        try:
            data = await _execute(
                context=context,
                device=device,
                action="screenshot",
                arguments={},
            )
        except MobileAgentError as exc:
            return _failed("phone_screenshot", exc.code, exc.message)
        return _completed(
            "phone_screenshot",
            safe_for_model="已完成手机截图。",
            data=data,
        )

    async def screen_ocr_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneScreenOcrArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_screen_ocr", "phone_offline", "手机 Agent 当前不在线")
        try:
            data = await _execute(
                context=context,
                device=device,
                action="ocr",
                arguments={},
                timeout_seconds=25,
            )
        except MobileAgentError as exc:
            return _failed("phone_screen_ocr", exc.code, exc.message)
        text = str(data.get("text") or "")[:6000]
        return _completed(
            "phone_screen_ocr",
            safe_for_model=f"手机屏幕 OCR 文本：\n{text}",
            data=data,
        )

    async def launch_app_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneLaunchAppArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_launch_app", "phone_offline", "手机 Agent 当前不在线")
        try:
            data = await _execute(
                context=context,
                device=device,
                action="launch_app",
                arguments={"package": parsed.package},
                timeout_seconds=25,
            )
        except MobileAgentError as exc:
            return _failed("phone_launch_app", exc.code, exc.message)
        return _completed(
            "phone_launch_app",
            safe_for_model=f"已请求打开手机应用：{parsed.package}",
            data=data,
        )

    async def action_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneActionArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_action", "phone_offline", "手机 Agent 当前不在线")
        args = {"kind": parsed.kind}
        if parsed.kind == "tap":
            args.update({"x": parsed.x, "y": parsed.y})
        elif parsed.kind in {"tap_text", "text"}:
            args["text"] = parsed.text
        try:
            data = await _execute(
                context=context,
                device=device,
                action="action",
                arguments=args,
            )
        except MobileAgentError as exc:
            return _failed("phone_action", exc.code, exc.message)
        return _completed(
            "phone_action",
            safe_for_model=f"手机动作已执行：{parsed.kind}",
            data=data,
        )

    async def play_music_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhonePlayMusicArguments.model_validate(arguments)
        try:
            result = await run_app_skill(
                user_id=context.user_id,
                skill="netmusic",
                action="play",
                parameters={"query": parsed.query},
                device_id=parsed.device_id,
            )
        except AppSkillError as exc:
            return _failed("phone_play_music", exc.code, exc.message)
        except MobileAgentError as exc:
            return _failed("phone_play_music", exc.code, exc.message)
        playing = bool(result.data.get("playing"))
        return _completed(
            "phone_play_music",
            safe_for_model=(
                f"已在网易云音乐处理“{parsed.query}”，"
                f"{'正在播放' if playing else '已选择歌曲但未确认播放'}。"
            ),
            data={"device_id": result.device_id, **result.data},
        )

    async def bilibili_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneBilibiliArguments.model_validate(arguments)
        try:
            result = await run_app_skill(
                user_id=context.user_id,
                skill="bilibili",
                action=parsed.action,
                parameters={"query": parsed.query},
                device_id=parsed.device_id,
            )
        except AppSkillError as exc:
            return _failed("phone_bilibili", exc.code, exc.message)
        except MobileAgentError as exc:
            return _failed("phone_bilibili", exc.code, exc.message)
        summary = (
            f"已在B站处理“{parsed.query}”，"
            f"{'评论页已打开' if parsed.action == 'comments' else '视频已打开'}"
        )
        return _completed(
            "phone_bilibili",
            safe_for_model=summary,
            data={"device_id": result.device_id, **result.data},
        )

    async def douyin_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneDouyinArguments.model_validate(arguments)
        try:
            result = await run_app_skill(
                user_id=context.user_id,
                skill="douyin",
                action=parsed.action,
                parameters={"query": parsed.query, "count": parsed.count},
                device_id=parsed.device_id,
            )
        except AppSkillError as exc:
            return _failed("phone_douyin", exc.code, exc.message)
        except MobileAgentError as exc:
            return _failed("phone_douyin", exc.code, exc.message)
        if parsed.action == "feed":
            summary = f"已打开抖音并刷了 {result.data.get('swiped', 0)} 条视频。"
        elif parsed.action == "search":
            summary = f"已在抖音搜索“{parsed.query}”。"
        elif parsed.action == "comments":
            summary = f"已打开抖音“{parsed.query}”相关视频的评论。"
        else:
            summary = f"已打开抖音“{parsed.query}”相关视频。"
        return _completed(
            "phone_douyin",
            safe_for_model=summary,
            data={"device_id": result.device_id, **result.data},
        )

    async def wechat_send_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ):
        parsed = PhoneWechatSendArguments.model_validate(arguments)
        try:
            result = await run_app_skill(
                user_id=context.user_id,
                skill="wechat",
                action="send",
                parameters={"text": parsed.text},
                device_id=parsed.device_id,
            )
        except AppSkillError as exc:
            return _failed("phone_wechat_send", exc.code, exc.message)
        except MobileAgentError as exc:
            return _failed("phone_wechat_send", exc.code, exc.message)
        if not result.data.get("sent"):
            return _failed(
                "phone_wechat_send",
                "send_unconfirmed",
                "消息已提交，但没有在微信界面确认到发送成功",
            )
        return _completed(
            "phone_wechat_send",
            safe_for_model=f"已通过微信给叶子发送消息：{parsed.text[:80]}",
            data={"device_id": result.device_id, **result.data},
        )

    async def xiaohongshu_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ):
        parsed = PhoneXiaohongshuArguments.model_validate(arguments)
        try:
            result = await run_app_skill(
                user_id=context.user_id,
                skill="xiaohongshu",
                action=parsed.action,
                parameters={"query": parsed.query, "count": parsed.count},
                device_id=parsed.device_id,
            )
        except AppSkillError as exc:
            return _failed("phone_xiaohongshu", exc.code, exc.message)
        except MobileAgentError as exc:
            return _failed("phone_xiaohongshu", exc.code, exc.message)
        labels = {
            "feed": f"已打开小红书并刷了 {result.data.get('swiped', 0)} 篇笔记。",
            "search": f"已在小红书搜索“{parsed.query}”。",
            "open": f"已打开小红书“{parsed.query}”相关笔记。",
            "comments": f"已打开小红书“{parsed.query}”相关笔记的评论。",
        }
        return _completed(
            "phone_xiaohongshu",
            safe_for_model=labels[parsed.action],
            data={"device_id": result.device_id, **result.data},
        )

    async def notifications_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneNotificationsArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_notifications", "phone_offline", "手机 Agent 当前不在线")
        try:
            data = await _execute(
                context=context,
                device=device,
                action="notifications",
                arguments={},
            )
        except MobileAgentError as exc:
            return _failed("phone_notifications", exc.code, exc.message)
        items = data.get("notifications") or []
        lines = [
            f"- {item.get('package', '')}: {item.get('title', '')} "
            f"{item.get('text', '')}"[:220]
            for item in items[:10]
            if isinstance(item, dict)
        ]
        return _completed(
            "phone_notifications",
            safe_for_model="手机通知：\n" + ("\n".join(lines) or "没有可读通知"),
            data=data,
        )

    async def stop_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneStopArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_stop", "phone_offline", "手机 Agent 当前不在线")
        try:
            await _execute(
                context=context,
                device=device,
                action="stop",
                arguments={},
                timeout_seconds=10,
            )
        except MobileAgentError as exc:
            return _failed("phone_stop", exc.code, exc.message)
        return _completed("phone_stop", safe_for_model="已向手机发送紧急停止。")

    async def run_task_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = PhoneRunTaskArguments.model_validate(arguments)
        device = _online_device(context.user_id, parsed.device_id)
        if device is None:
            return _failed("phone_run_task", "phone_offline", "手机 Agent 当前不在线")
        history: list[dict[str, Any]] = []
        for step in range(parsed.max_steps):
            try:
                data = await _execute(
                    context=context,
                    device=device,
                    action="observe",
                    arguments={},
                )
            except MobileAgentError as exc:
                return _failed("phone_run_task", exc.code, exc.message)
            ui_text = str(data.get("text") or "")[:5000]
            prompt = (
                "你在控制一台安卓手机。根据任务和当前 UI，决定下一步只做一个动作。"
                "只输出 JSON，不要 Markdown。字段："
                '{"action":"tap_text|tap|back|home|launch_app|done|fail",'
                '"text":"用于tap_text的文字","x":0,"y":0,'
                '"package":"用于launch_app的包名","message":"完成或失败说明"}。'
                "动作必须能在当前界面执行；无法完成时输出 fail。"
            )
            try:
                response = await get_llm_provider().chat_completion_message(
                    messages=[
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "task": parsed.task,
                                    "step": step + 1,
                                    "ui": ui_text,
                                    "history": history[-5:],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    thinking={"type": "disabled"},
                    temperature=0.1,
                    max_tokens=300,
                )
                planned = json.loads(response.content.strip())
            except Exception as exc:
                return _failed(
                    "phone_run_task",
                    "planner_failed",
                    f"手机任务规划失败：{exc}",
                )
            action = str(planned.get("action") or "").strip()
            if action == "done":
                return _completed(
                    "phone_run_task",
                    safe_for_model=str(planned.get("message") or "手机任务完成。"),
                    data={"steps": step + 1, "history": history},
                )
            if action == "fail":
                return _failed(
                    "phone_run_task",
                    "task_failed",
                    str(planned.get("message") or "手机任务无法完成。"),
                )
            try:
                if action == "launch_app":
                    await _execute(
                        context=context,
                        device=device,
                        action="launch_app",
                        arguments={"package": str(planned.get("package") or "")},
                    )
                elif action == "tap":
                    await _execute(
                        context=context,
                        device=device,
                        action="action",
                        arguments={
                            "kind": "tap",
                            "x": int(planned.get("x") or 0),
                            "y": int(planned.get("y") or 0),
                        },
                    )
                elif action == "tap_text":
                    await _execute(
                        context=context,
                        device=device,
                        action="action",
                        arguments={
                            "kind": "tap_text",
                            "text": str(planned.get("text") or ""),
                        },
                    )
                elif action in {"back", "home"}:
                    await _execute(
                        context=context,
                        device=device,
                        action="action",
                        arguments={"kind": action},
                    )
                else:
                    return _failed(
                        "phone_run_task",
                        "planner_action_unsupported",
                        f"不支持的动作：{action}",
                    )
            except MobileAgentError as exc:
                return _failed("phone_run_task", exc.code, exc.message)
            history.append(planned)
        return _failed(
            "phone_run_task",
            "task_step_limit",
            f"手机任务在 {parsed.max_steps} 步内没有完成。",
        )

    _register(
        registry,
        name="phone_status",
        description="查看用户已配对的安卓手机 Agent 是否在线。",
        arguments_model=PhoneStatusArguments,
        handler=status_handler,
        risk=ToolRisk.READ,
        timeout_seconds=15,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_observe",
        description=(
            "读取安卓手机当前界面、UI 树和前台应用。"
            "需要知道手机上现在显示什么时使用；可选返回截图。"
        ),
        arguments_model=PhoneObserveArguments,
        handler=observe_handler,
        risk=ToolRisk.READ,
        timeout_seconds=35,
        max_calls=4,
    )
    _register(
        registry,
        name="phone_screenshot",
        description="截取安卓手机当前屏幕。截图只用于当前任务，不写入聊天。",
        arguments_model=PhoneScreenshotArguments,
        handler=screenshot_handler,
        risk=ToolRisk.READ,
        timeout_seconds=25,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_screen_ocr",
        description=(
            "截取手机当前屏幕并做中文 OCR，返回文字和坐标块。"
            "用于微信聊天页、其他应用界面等无障碍读不到的场景。"
        ),
        arguments_model=PhoneScreenOcrArguments,
        handler=screen_ocr_handler,
        risk=ToolRisk.READ,
        timeout_seconds=30,
        max_calls=3,
    )
    _register(
        registry,
        name="phone_launch_app",
        description="在安卓手机上按包名启动一个应用。",
        arguments_model=PhoneLaunchAppArguments,
        handler=launch_app_handler,
        risk=ToolRisk.CREATE_INTERNAL,
        timeout_seconds=40,
        max_calls=4,
    )
    _register(
        registry,
        name="phone_action",
        description=(
            "在安卓手机上点击、按文字点击、输入、返回、Home 或最近任务。"
            "只操作用户明确要求操作的手机。"
        ),
        arguments_model=PhoneActionArguments,
        handler=action_handler,
        risk=ToolRisk.DESTRUCTIVE,
        timeout_seconds=35,
        max_calls=8,
    )
    _register(
        registry,
        name="phone_play_music",
        description=(
            "在网易云音乐里搜索歌曲或歌手，选择第一条结果并播放。"
            "只用于音乐播放，不处理支付、账号或评论发布。"
        ),
        arguments_model=PhonePlayMusicArguments,
        handler=play_music_handler,
        risk=ToolRisk.READ,
        timeout_seconds=60,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_wechat_send",
        description=(
            "通过专用微信账号给唯一联系人“叶子”发送文本消息。"
            "不允许任意联系人、群聊、图片或文件。"
        ),
        arguments_model=PhoneWechatSendArguments,
        handler=wechat_send_handler,
        risk=ToolRisk.SEND,
        timeout_seconds=60,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_xiaohongshu",
        description=(
            "打开小红书刷笔记、搜索笔记、打开搜索结果或查看评论。"
            "只做浏览，不发评论、不私信、不购物。"
        ),
        arguments_model=PhoneXiaohongshuArguments,
        handler=xiaohongshu_handler,
        risk=ToolRisk.READ,
        timeout_seconds=60,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_douyin",
        description=(
            "打开抖音刷视频、搜索视频、打开搜索结果或查看评论。"
            "只做浏览，不发评论、不私信、不购物。"
        ),
        arguments_model=PhoneDouyinArguments,
        handler=douyin_handler,
        risk=ToolRisk.READ,
        timeout_seconds=60,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_bilibili",
        description=(
            "在B站搜索视频并打开播放页，或继续打开评论区。"
            "只用于浏览视频/评论，不发评论、不登录账号。"
        ),
        arguments_model=PhoneBilibiliArguments,
        handler=bilibili_handler,
        risk=ToolRisk.READ,
        timeout_seconds=60,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_notifications",
        description="读取安卓手机当前通知列表，只读，不点击通知。",
        arguments_model=PhoneNotificationsArguments,
        handler=notifications_handler,
        risk=ToolRisk.READ,
        timeout_seconds=20,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_stop",
        description="紧急停止手机 Agent 当前动作。",
        arguments_model=PhoneStopArguments,
        handler=stop_handler,
        risk=ToolRisk.CREATE_INTERNAL,
        timeout_seconds=15,
        max_calls=2,
    )
    _register(
        registry,
        name="phone_run_task",
        description=(
            "把一个手机任务交给手机 Agent 多步执行，例如打开设置、搜索信息、"
            "启动应用并完成简单操作。复杂或高风险任务不要使用。"
        ),
        arguments_model=PhoneRunTaskArguments,
        handler=run_task_handler,
        risk=ToolRisk.DESTRUCTIVE,
        timeout_seconds=180,
        max_calls=1,
    )
