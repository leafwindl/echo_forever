from __future__ import annotations

from typing import Literal

from providers.vision_provider import VisionUnavailableError, describe_desktop_image
from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
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


class DesktopMusicSearchArguments(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=160,
        description="要搜索并播放的歌曲或歌手。",
    )


class DesktopNotepadWriteArguments(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=2000,
        description="要写进新记事本窗口的文字。",
    )


class DesktopDshTaskArguments(BaseModel):
    instruction: str = Field(
        min_length=1,
        max_length=2000,
        description="交给 DSH 的独立任务描述。",
    )
    workspace: str = Field(
        default="",
        max_length=300,
        description="可选工作目录；留空使用用户主目录。",
    )


class DesktopSpeakArguments(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=500,
        description="要在电脑扬声器上朗读的文字。",
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

    async def music_search_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopMusicSearchArguments.model_validate(arguments)
        return await _run_desktop_action(
            context=context,
            tool_name="desktop_music_search_play",
            action="music_search_play",
            arguments=parsed.model_dump(),
            timeout_seconds=65,
        )

    async def notepad_write_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopNotepadWriteArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="notepad_write",
                arguments=parsed.model_dump(),
                timeout_seconds=45,
            )
        except DesktopError as exc:
            return _failed("desktop_notepad_write", exc.code, exc.message)
        return _completed(
            "desktop_notepad_write",
            safe_for_model=(
                f"已在记事本写入 {result.data.get('char_count', 0)} 个字，"
                "默认没有保存文件。"
            ),
            data={"node_id": result.node_id, "char_count": result.data.get("char_count")},
        )

    async def dsh_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopDshTaskArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="dsh_task",
                arguments=parsed.model_dump(),
                timeout_seconds=320,
            )
        except DesktopError as exc:
            return _failed("desktop_dsh_task", exc.code, exc.message)
        output = str(result.data.get("result") or "").strip()
        if not output:
            return _failed(
                "desktop_dsh_task",
                "dsh_empty_result",
                "DSH 结束了，但没有返回可用结果。",
            )
        return _completed(
            "desktop_dsh_task",
            safe_for_model=f"DSH 最终结果：\n{output[:6000]}",
            data={
                "node_id": result.node_id,
                "workspace": result.data.get("workspace"),
                "exit_code": result.data.get("exit_code"),
            },
        )

    async def speak_handler(context: ToolExecutionContext, arguments: BaseModel):
        parsed = DesktopSpeakArguments.model_validate(arguments)
        try:
            result = await execute_desktop_action(
                user_id=context.user_id,
                action="speak",
                arguments={"text": parsed.text},
                timeout_seconds=60,
            )
        except DesktopError as exc:
            return _failed("desktop_speak", exc.code, exc.message)
        return _completed(
            "desktop_speak",
            safe_for_model="电脑扬声器已开始朗读。",
            data={"node_id": result.node_id, "char_count": len(parsed.text)},
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
        name="desktop_speak",
        description=(
            "在用户电脑扬声器朗读文字，不能代替普通回复。"
        ),
        arguments_model=DesktopSpeakArguments,
        handler=speak_handler,
        timeout_seconds=70,
        max_calls=2,
    )
    _register(
        registry,
        name="desktop_status",
        description="查看用户电脑节点是否在线。",
        arguments_model=DesktopStatusArguments,
        handler=status_handler,
        timeout_seconds=10,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_open_app",
        description=(
            "在用户电脑上打开允许的应用，电脑端会弹窗批准。"
        ),
        arguments_model=DesktopOpenAppArguments,
        handler=open_app_handler,
        timeout_seconds=55,
        max_calls=2,
    )
    _register(
        registry,
        name="desktop_media_control",
        description=(
            "控制用户电脑上正在播放的网易云音乐：播放/暂停、下一首、上一首；"
            "电脑端会请求本地批准。"
        ),
        arguments_model=DesktopMediaArguments,
        handler=media_handler,
        timeout_seconds=50,
        max_calls=3,
    )
    _register(
        registry,
        name="desktop_look",
        description=(
            "通过用户电脑摄像头看一眼并描述画面，结果带回对话；"
            "电脑端每次都会弹出摄像头批准窗口，用户拒绝就失败。"
        ),
        arguments_model=DesktopLookArguments,
        handler=look_handler,
        timeout_seconds=70,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_music_search_play",
        description=(
            "在用户电脑的网易云音乐里搜索并播放指定歌曲或歌手；"
            "电脑端会请求本地批准。"
        ),
        arguments_model=DesktopMusicSearchArguments,
        handler=music_search_handler,
        timeout_seconds=75,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_notepad_write",
        description=(
            "在用户电脑上打开新的记事本窗口并写入指定文字；"
            "默认不保存文件、不覆盖已有文档。"
        ),
        arguments_model=DesktopNotepadWriteArguments,
        handler=notepad_write_handler,
        timeout_seconds=55,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_dsh_task",
        description=(
            "让用户电脑上的 DSH 执行任务并返回结果；会弹窗批准。"
        ),
        arguments_model=DesktopDshTaskArguments,
        handler=dsh_handler,
        timeout_seconds=340,
        max_calls=1,
    )
    _register(
        registry,
        name="desktop_screenshot",
        description=(
            "截取用户电脑当前屏幕并描述屏幕内容；"
            "电脑端会弹出截图批准窗口。"
        ),
        arguments_model=DesktopScreenArguments,
        handler=screenshot_handler,
        timeout_seconds=70,
        max_calls=1,
    )


__all__ = ["register_desktop_tools"]
