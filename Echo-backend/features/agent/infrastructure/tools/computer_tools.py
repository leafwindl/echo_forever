from __future__ import annotations

import asyncio
import json
import time

from providers.vision_provider import VisionUnavailableError, describe_desktop_image
from pydantic import BaseModel, Field

from features.agent.domain.entities import AgentToolResult, AgentToolStatus, ToolSpecification
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.desktop.domain.entities import DesktopError
from features.desktop.public import execute_desktop_action

# Echo 自有计算机（虚拟机）的工具面：完全自由，不需要用户授权。
# 与 desktop_* 的区别只在于目标节点是 owner_type="echo"，不是用户的电脑。


class ComputerScreenshotArguments(BaseModel):
    question: str = Field(
        default="请用中文简短描述当前屏幕上的内容。",
        max_length=300,
        description="问题。",
    )


class ComputerClickArguments(BaseModel):
    x: int = Field(ge=0, le=20000, description="x")
    y: int = Field(ge=0, le=20000, description="y")
    right: bool = Field(default=False, description="right")


class ComputerTypeArguments(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ComputerKeyArguments(BaseModel):
    keys: str = Field(min_length=1, max_length=100)


class ComputerExecArguments(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


class ComputerLaunchArguments(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class WechatSendArguments(BaseModel):
    contact: str = Field(min_length=1)
    text: str = ""
    items: list[dict] = []


class WechatMessagesArguments(BaseModel):
    chat: str = Field(min_length=1, max_length=80, description="微信会话名。")
    limit: int = Field(default=10, ge=1, le=50)


class WechatSessionsArguments(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


def _failed(tool_name: str, code: str, message: str) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.FAILED,
        error_code=code,
        safe_for_model=message,
    )


def _completed(
    tool_name: str,
    *,
    safe_for_model: str,
    data: dict | None = None,
) -> AgentToolResult:
    return AgentToolResult(
        call_id="",
        tool_name=tool_name,
        status=AgentToolStatus.COMPLETED,
        data=data or {},
        safe_for_model=safe_for_model,
    )


async def _run_computer_action(
    *,
    context: ToolExecutionContext,
    tool_name: str,
    action: str,
    arguments: dict,
    safe_for_model: str,
    timeout_seconds: int = 45,
) -> AgentToolResult:
    try:
        result = await execute_desktop_action(
            user_id=context.user_id,
            action=action,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
            owner_type="echo",
        )
    except DesktopError as exc:
        return _failed(tool_name, exc.code, exc.message)
    return _completed(
        tool_name,
        safe_for_model=safe_for_model,
        data={
            "node_id": result.node_id,
            "action": action,
            "result": result.data,
        },
    )


def _register(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    arguments_model,
    handler,
    timeout_seconds: int,
    max_calls: int = 3,
) -> None:
    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name=name,
                description=description,
                timeout_seconds=timeout_seconds,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=max_calls,
                max_successful_calls_per_turn=max_calls,
            ),
            arguments_model=arguments_model,
            handler=handler,
        )
    )


def register_computer_tools(registry: ToolRegistry) -> None:
    async def screenshot_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerScreenshotArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="screen_capture",
                arguments={"question": parsed.question},
                timeout_seconds=55,
                owner_type="echo",
            )
        except DesktopError as exc:
            return _failed("computer_screenshot", exc.code, exc.message)
        image = result.data.get("image_base64")
        mime_type = str(result.data.get("mime_type") or "image/jpeg")
        if not isinstance(image, str) or not image:
            return _failed("computer_screenshot", "capture_missing", "没有收到屏幕截图。")
        try:
            description = await describe_desktop_image(
                image_base64=image,
                mime_type=mime_type,
                question=parsed.question,
            )
        except VisionUnavailableError:
            return _failed(
                "computer_screenshot",
                "vision_unavailable",
                "截图已经拿到，但视觉模型暂时不可用，不能声称看到了内容。",
            )
        except Exception:
            return _failed(
                "computer_screenshot",
                "vision_failed",
                "截图已经拿到，但视觉识别失败，不能声称看到了内容。",
            )
        return _completed(
            "computer_screenshot",
            safe_for_model=f"你自己电脑的画面：{description}",
            data={
                "node_id": result.node_id,
                "description": description,
                "captured_at": result.data.get("captured_at"),
            },
        )

    async def click_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerClickArguments.model_validate(arguments)
        return await _run_computer_action(
            context=context,
            tool_name="computer_click",
            action="click",
            arguments={"x": parsed.x, "y": parsed.y, "right": parsed.right},
            safe_for_model=f"已在 ({parsed.x}, {parsed.y}) 点击。",
        )

    async def type_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerTypeArguments.model_validate(arguments)
        return await _run_computer_action(
            context=context,
            tool_name="computer_type",
            action="type",
            arguments={"text": parsed.text},
            safe_for_model=f"已输入 {len(parsed.text)} 个字符。",
        )

    async def key_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerKeyArguments.model_validate(arguments)
        return await _run_computer_action(
            context=context,
            tool_name="computer_key",
            action="key",
            arguments={"keys": parsed.keys},
            safe_for_model=f"已发送按键 {parsed.keys}。",
        )

    async def _run_remote_command(
        context: ToolExecutionContext,
        command: str,
        timeout_seconds: int = 120,
    ) -> tuple[bool, str, int | None]:
        """通过 agent 执行命令并等待结果，返回 (ok, output, exit_code)。"""
        try:
            start = await execute_desktop_action(
                user_id=context.user_id,
                action="exec",
                arguments={"command": command},
                timeout_seconds=30,
                owner_type="echo",
            )
        except DesktopError as exc:
            return False, exc.message, None

        # 旧版 agent 会同步返回输出；新版返回 job_id，需要轮询结果
        job_id = start.data.get("job_id")
        if job_id is None:
            return (
                True,
                str(start.data.get("output") or "").strip(),
                start.data.get("exit_code"),
            )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            try:
                result = await execute_desktop_action(
                    user_id=context.user_id,
                    action="job_result",
                    arguments={"job_id": job_id},
                    timeout_seconds=20,
                    owner_type="echo",
                )
            except DesktopError as exc:
                return False, exc.message, None
            status = str(result.data.get("status") or "")
            if status == "done":
                return (
                    True,
                    str(result.data.get("output") or "").strip(),
                    result.data.get("exit_code"),
                )
            if status in {"failed", "missing"}:
                return False, str(result.data.get("output") or status).strip(), None
        return False, "命令执行超过时限仍未完成。", None

    async def exec_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerExecArguments.model_validate(arguments)
        ok, output, exit_code = await _run_remote_command(context, parsed.command)
        if not ok:
            return _failed("computer_exec", "exec_failed", output)
        return _completed(
            "computer_exec",
            safe_for_model=(
                f"命令已执行（exit={exit_code}）：\n{output[:3000]}"
                if output
                else f"命令已执行（exit={exit_code}），没有输出。"
            ),
            data={"exit_code": exit_code, "output": output[:8000]},
        )

    def _bridge_command(path: str, payload: dict | None = None) -> str:
        base = "http://127.0.0.1:8765"
        if payload is None:
            return (
                f"Invoke-RestMethod -Uri '{base}{path}' -TimeoutSec 120 "
                "| ConvertTo-Json -Compress -Depth 6"
            )
        body = json.dumps(payload, ensure_ascii=False).replace("'", "''")
        return (
            f"Invoke-RestMethod -Uri '{base}{path}' -Method Post "
            "-ContentType 'application/json; charset=utf-8' "
            f"-Body '{body}' -TimeoutSec 180 | ConvertTo-Json -Compress -Depth 6"
        )

    async def wechat_send_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = WechatSendArguments.model_validate(arguments)
        command = _bridge_command("/send", {"to": parsed.contact, "text": parsed.text})
        if parsed.items:
            command = _bridge_command("/send_sequence", {"items": parsed.items})
        ok, output, _ = await _run_remote_command(context, command, timeout_seconds=150)
        if not ok:
            # bridge 已把“已操作发送”归一成成功；走到这里是真的没发出去
            return _failed("wechat_send", "wechat_send_failed", output[:800])
        return _completed(
            "wechat_send",
            safe_for_model=(
                "消息已通过微信发出去了。如果输出里提到“数据库回读未确认”，"
                "那是微信 WAL 读取的已知限制，不影响送达，不用再发一次。"
                f"\n{output[:900]}"
            ),
            data={"output": output[:4000], "confirmed": True},
        )

    async def wechat_messages_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = WechatMessagesArguments.model_validate(arguments)
        command = _bridge_command(
            "/messages",
            {"chat": parsed.chat, "limit": parsed.limit},
        )
        ok, output, _ = await _run_remote_command(context, command, timeout_seconds=120)
        if not ok:
            return _failed("wechat_messages", "wechat_messages_failed", output[:800])
        return _completed(
            "wechat_messages",
            safe_for_model=f"微信消息：{output[:2500]}",
            data={"output": output[:6000]},
        )

    async def wechat_sessions_handler(context: ToolExecutionContext, arguments: BaseModel):
        WechatSessionsArguments.model_validate(arguments)
        ok, output, _ = await _run_remote_command(
            context,
            _bridge_command("/sessions"),
            timeout_seconds=90,
        )
        if not ok:
            return _failed("wechat_sessions", "wechat_sessions_failed", output[:800])
        return _completed(
            "wechat_sessions",
            safe_for_model=f"微信会话：{output[:2000]}",
            data={"output": output[:4000]},
        )

    async def launch_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = ComputerLaunchArguments.model_validate(arguments)
        return await _run_computer_action(
            context=context,
            tool_name="computer_launch",
            action="launch",
            arguments={"path": parsed.path},
            safe_for_model=f"已启动 {parsed.path[:120]}。",
            timeout_seconds=30,
        )

    _register(
        registry,
        name="computer_screenshot",
        description="看你自己的电脑屏幕，不需要用户许可。",
        arguments_model=ComputerScreenshotArguments,
        handler=screenshot_handler,
        timeout_seconds=60,
        max_calls=4,
    )
    _register(
        registry,
        name="computer_click",
        description="在你自己的电脑上按坐标点击。",
        arguments_model=ComputerClickArguments,
        handler=click_handler,
        timeout_seconds=30,
        max_calls=12,
    )
    _register(
        registry,
        name="computer_type",
        description="在你自己的电脑上输入文本。",
        arguments_model=ComputerTypeArguments,
        handler=type_handler,
        timeout_seconds=30,
        max_calls=8,
    )
    _register(
        registry,
        name="computer_key",
        description="在你自己的电脑上发送按键，如 {ENTER}、^a。",
        arguments_model=ComputerKeyArguments,
        handler=key_handler,
        timeout_seconds=30,
        max_calls=8,
    )
    _register(
        registry,
        name="computer_exec",
        description="在你自己的电脑上执行 PowerShell 命令。",
        arguments_model=ComputerExecArguments,
        handler=exec_handler,
        timeout_seconds=100,
        max_calls=4,
    )
    _register(
        registry,
        name="computer_launch",
        description="在你自己的电脑上启动程序。",
        arguments_model=ComputerLaunchArguments,
        handler=launch_handler,
        timeout_seconds=40,
        max_calls=4,
    )
    _register(
        registry,
        name="wechat_send",
        description="用你电脑上登录的微信给联系人发消息。",
        arguments_model=WechatSendArguments,
        handler=wechat_send_handler,
        timeout_seconds=170,
        max_calls=4,
    )
    _register(
        registry,
        name="wechat_messages",
        description="读取微信某个会话的最近消息，不操作界面。",
        arguments_model=WechatMessagesArguments,
        handler=wechat_messages_handler,
        timeout_seconds=130,
        max_calls=6,
    )
    _register(
        registry,
        name="wechat_sessions",
        description="列出微信会话列表，不操作界面。",
        arguments_model=WechatSessionsArguments,
        handler=wechat_sessions_handler,
        timeout_seconds=100,
        max_calls=6,
    )


__all__ = ["register_computer_tools"]
