from __future__ import annotations

from typing import Literal

from providers.vision_provider import VisionUnavailableError, describe_desktop_image
from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolRisk,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.desktop.domain.entities import DesktopError
from features.desktop.public import execute_desktop_action, list_desktop_nodes


class DesktopOpenAppArguments(BaseModel):
    app: Literal["netease_cloud_music", "notepad", "calculator"] = Field(
        description="要打开的应用；netease_cloud_music 是网易云音乐。"
    )


class DesktopMediaArguments(BaseModel):
    action: Literal["play_pause", "next", "previous"] = Field(
        description="媒体控制动作。"
    )


class DesktopLookArguments(BaseModel):
    question: str = Field(
        default="请用中文简短描述你现在看到的内容。",
        max_length=300,
        description="希望 Echo 观察并回答的问题。",
    )


class DesktopScreenArguments(BaseModel):
    question: str = Field(
        default="请用中文简短描述当前屏幕上的内容。",
        max_length=300,
        description="希望 Echo 观察并回答的问题。",
    )


class DesktopStatusArguments(BaseModel):
    pass


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


async def _run_desktop_action(
    *,
    context: ToolExecutionContext,
    tool_name: str,
    action: str,
    arguments: dict,
    timeout_seconds: int = 45,
) -> AgentToolResult:
    try:
        result = await execute_desktop_action(
            user_id=context.user_id,
            action=action,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
    except DesktopError as exc:
        return _failed(tool_name, exc.code, exc.message)
    return _completed(
        tool_name,
        safe_for_model=f"电脑操作已完成：{action}",
        data={"node_id": result.node_id, "action": action},
    )


def _register(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    arguments_model,
    handler,
    risk: ToolRisk,
    timeout_seconds: int,
    max_calls: int = 3,
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


def register_desktop_tools(registry: ToolRegistry) -> None:
    async def open_app_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopOpenAppArguments.model_validate(arguments)
        return await _run_desktop_action(
            context=context,
            tool_name="desktop_open_app",
            action="open_app",
            arguments=parsed.model_dump(),
        )

    async def media_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopMediaArguments.model_validate(arguments)
        return await _run_desktop_action(
            context=context,
            tool_name="desktop_media_control",
            action="media_control",
            arguments=parsed.model_dump(),
        )

    async def look_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopLookArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="camera_capture",
                arguments={"question": parsed.question},
                timeout_seconds=55,
            )
        except DesktopError as exc:
            return _failed("desktop_look", exc.code, exc.message)
        image = result.data.get("image_base64")
        mime_type = str(result.data.get("mime_type") or "image/jpeg")
        if not isinstance(image, str) or not image:
            return _failed("desktop_look", "capture_missing", "没有收到摄像头画面。")
        try:
            description = await describe_desktop_image(
                image_base64=image,
                mime_type=mime_type,
                question=parsed.question,
            )
        except VisionUnavailableError:
            return _failed(
                "desktop_look",
                "vision_unavailable",
                "摄像头画面已经拍到，但视觉模型暂时不可用，不能声称看到了内容。",
            )
        except Exception:
            return _failed(
                "desktop_look",
                "vision_failed",
                "摄像头画面已经拍到，但视觉识别失败，不能声称看到了内容。",
            )
        return _completed(
            "desktop_look",
            safe_for_model=f"摄像头画面描述：{description}",
            data={
                "node_id": result.node_id,
                "description": description,
                "captured_at": result.data.get("captured_at"),
            },
        )

    async def screenshot_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopScreenArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="screen_capture",
                arguments={"question": parsed.question},
                timeout_seconds=55,
            )
        except DesktopError as exc:
            return _failed("desktop_screenshot", exc.code, exc.message)
        image = result.data.get("image_base64")
        mime_type = str(result.data.get("mime_type") or "image/png")
        if not isinstance(image, str) or not image:
            return _failed("desktop_screenshot", "capture_missing", "没有收到屏幕截图。")
        try:
            description = await describe_desktop_image(
                image_base64=image,
                mime_type=mime_type,
                question=parsed.question,
            )
        except VisionUnavailableError:
            return _failed(
                "desktop_screenshot",
                "vision_unavailable",
                "屏幕截图已经拿到，但视觉模型暂时不可用，不能声称看到了内容。",
            )
        except Exception:
            return _failed(
                "desktop_screenshot",
                "vision_failed",
                "屏幕截图已经拿到，但视觉识别失败，不能声称看到了内容。",
            )
        return _completed(
            "desktop_screenshot",
            safe_for_model=f"屏幕画面描述：{description}",
            data={
                "node_id": result.node_id,
                "description": description,
                "captured_at": result.data.get("captured_at"),
            },
        )

    async def status_handler(context: ToolExecutionContext, arguments: BaseModel):
        DesktopStatusArguments.model_validate(arguments)
        nodes = list_desktop_nodes(context.user_id)
        if not nodes:
            return _completed(
                "desktop_status",
                safe_for_model="还没有配对电脑；需要先在电脑上运行 Echo Desktop 并完成配对。",
                data={"nodes": []},
            )
        online = [item for item in nodes if item.online]
        if not online:
            return _completed(
                "desktop_status",
                safe_for_model="电脑节点已配对，但当前不在线；不能执行电脑操作。",
                data={"nodes": [item.node.node_id for item in nodes], "online": False},
            )
        names = "、".join(item.node.name for item in online)
        return _completed(
            "desktop_status",
            safe_for_model=f"电脑节点在线：{names}。",
            data={
                "nodes": [
                    {
                        "node_id": item.node.node_id,
                        "name": item.node.name,
                        "online": item.online,
                        "capabilities": list(item.node.capabilities),
                    }
                    for item in nodes
                ],
                "online": True,
            },
        )

    _register(
        registry,
        name="desktop_status",
        description=(
            "查看用户电脑上的 Echo Desktop 是否在线。只有在线时才能操作电脑；"
            "用户提到自己的电脑、电脑上的软件或摄像头时可以先调用它。"
        ),
        arguments_model=DesktopStatusArguments,
        handler=status_handler,
        risk=ToolRisk.READ,
        timeout_seconds=10,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_open_app",
        description=(
            "在用户已配对的 Windows 电脑上打开允许的应用。当前只支持网易云音乐、记事本、计算器。"
            "用户明确要求打开电脑软件时才使用；不要在普通聊天里主动打开。"
            "执行前电脑端会弹出本地批准窗口，用户拒绝就会失败。"
        ),
        arguments_model=DesktopOpenAppArguments,
        handler=open_app_handler,
        risk=ToolRisk.CREATE_INTERNAL,
        timeout_seconds=55,
        max_calls=2,
    )
    _register(
        registry,
        name="desktop_media_control",
        description=(
            "控制用户电脑上正在播放的网易云音乐：播放/暂停、下一首、上一首。"
            "用户要求放歌、暂停、切歌时使用；电脑端会请求本地批准。"
        ),
        arguments_model=DesktopMediaArguments,
        handler=media_handler,
        risk=ToolRisk.CREATE_INTERNAL,
        timeout_seconds=50,
        max_calls=3,
    )
    _register(
        registry,
        name="desktop_look",
        description=(
            "通过用户电脑摄像头看一眼，并把看到的画面描述带回对话。"
            "仅当用户明确说“看看我”“看摄像头”时使用，不要主动偷看；"
            "电脑端每次都会弹出摄像头批准窗口，用户拒绝就失败。"
        ),
        arguments_model=DesktopLookArguments,
        handler=look_handler,
        risk=ToolRisk.READ,
        timeout_seconds=70,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_screenshot",
        description=(
            "截取用户电脑当前屏幕并描述屏幕内容。仅当用户明确要求看屏幕或"
            "需要确认电脑上的画面时使用；电脑端会弹出截图批准窗口。"
        ),
        arguments_model=DesktopScreenArguments,
        handler=screenshot_handler,
        risk=ToolRisk.READ,
        timeout_seconds=70,
        max_calls=1,
    )


__all__ = ["register_desktop_tools"]
