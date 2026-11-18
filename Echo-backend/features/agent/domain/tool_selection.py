"""按运行时事实决定本轮把哪些工具告诉模型。

这里只做纯判断：输入是已经查好的事实（设备是否在线、触发消息），输出是工具名
集合。查询本身在 application 层的 `tool_availability`，这样选择逻辑可以完全
单测，不需要数据库。

设计取舍：

- 交付与提醒常驻：高频且确定性强，拆包漏判的代价大于省下的 token。
- 设备状态工具常驻：即使设备离线，模型也要能如实回答"电脑/手机连了吗"。
- 设备操作工具按在线状态注入：离线时注入等于给模型一排按不动的按钮。
- 关系工具常驻：只有两个，且依赖关系阶段上下文，误判会让"用户同意推进"落空。
- 主动开关按关键词注入：低频操作，漏判只是多问一句，代价可控。
"""

from __future__ import annotations

from dataclasses import dataclass

# 常驻：交付 + 提醒。`search_web` 未配置时不会注册，注册表会自动忽略这个名字。
CORE_TOOL_NAMES = (
    "emit_chat_beats",
    "send_sticker",
    "create_chat_schedule",
    "list_chat_schedules",
    "cancel_chat_schedule",
    "search_web",
)

# 设备离线也保留：让模型能回答连接状态，而不是假装没这个能力。
DESKTOP_STATUS_TOOL = "desktop_status"
PHONE_STATUS_TOOL = "phone_status"

# 仅在对应设备在线时注入。status 已在上面单独处理。
DESKTOP_TOOL_NAMES = (
    "desktop_speak",
    "desktop_open_app",
    "desktop_media_control",
    "desktop_look",
    "desktop_music_search_play",
    "desktop_notepad_write",
    "desktop_dsh_task",
    "desktop_screenshot",
)

PHONE_TOOL_NAMES = (
    "phone_observe",
    "phone_screenshot",
    "phone_screen_ocr",
    "phone_launch_app",
    "phone_action",
    "phone_play_music",
    "phone_wechat_send",
    "phone_wechat_sticker",
    "phone_xiaohongshu",
    "phone_douyin",
    "phone_bilibili",
    "phone_notifications",
    "phone_stop",
    "phone_run_task",
)

RELATIONSHIP_TOOL_NAMES = (
    "propose_relationship",
    "respond_relationship",
)

PROACTIVE_TOOL_NAMES = (
    "pause_proactive_contact",
    "resume_proactive_contact",
)

# Echo 自己的虚拟机（owner_type=echo）。这些能力不需要用户授权，
# 与 desktop_* 的区别只在目标机器属于自己的电脑。
ECHO_COMPUTER_TOOL_NAMES = (
    "computer_screenshot",
    "computer_click",
    "computer_type",
    "computer_key",
    "computer_exec",
    "computer_launch",
    "wechat_send",
    "wechat_messages",
    "wechat_sessions",
)

_PROACTIVE_CONTACT_KEYWORDS = (
    "主动",
    "别找我",
    "不要找我",
    "暂停联系",
    "恢复联系",
)

# 主动模式下可自主使用的能力。刻意排除：
# - desktop_dsh_task：拥有电脑完整权限，需用户授权；
# - phone_wechat_send / phone_wechat_sticker：外发给第三人，需事先授权；
# - phone_run_task：手机多步执行，可能包含外发，需用户授权。
PROACTIVE_CORE_TOOL_NAMES = (
    "emit_chat_beats",
    "send_sticker",
    "search_web",
)
PROACTIVE_DESKTOP_TOOL_NAMES = tuple(
    name for name in DESKTOP_TOOL_NAMES if name != "desktop_dsh_task"
)
PROACTIVE_PHONE_TOOL_NAMES = tuple(
    name
    for name in PHONE_TOOL_NAMES
    if name not in {"phone_wechat_send", "phone_wechat_sticker", "phone_run_task"}
)


@dataclass(frozen=True)
class ToolSelectionContext:
    conversation_mode: str = "chat"
    trigger_message: str = ""
    desktop_online: bool = False
    phone_online: bool = False
    echo_computer_online: bool = False


def mentions_proactive_contact(message: str) -> bool:
    clean = " ".join(message.split())
    return any(keyword in clean for keyword in _PROACTIVE_CONTACT_KEYWORDS)


def select_chat_tool_names(context: ToolSelectionContext) -> tuple[str, ...] | None:
    """返回本轮允许注入的工具名；None 表示不限制（非 chat 模式维持原行为）。"""
    if context.conversation_mode != "chat":
        return None

    names = [
        *CORE_TOOL_NAMES,
        DESKTOP_STATUS_TOOL,
        PHONE_STATUS_TOOL,
        *RELATIONSHIP_TOOL_NAMES,
    ]
    if context.desktop_online:
        names.extend(DESKTOP_TOOL_NAMES)
    if context.phone_online:
        names.extend(PHONE_TOOL_NAMES)
    if context.echo_computer_online:
        names.extend(ECHO_COMPUTER_TOOL_NAMES)
    if mentions_proactive_contact(context.trigger_message):
        names.extend(PROACTIVE_TOOL_NAMES)
    return tuple(dict.fromkeys(names))


def select_proactive_tool_names(context: ToolSelectionContext) -> tuple[str, ...]:
    """主动 turn 的工具集：只用能自主执行的能力，排除需授权的能力。"""
    names = list(PROACTIVE_CORE_TOOL_NAMES)
    if context.desktop_online:
        names.extend(PROACTIVE_DESKTOP_TOOL_NAMES)
    if context.phone_online:
        names.extend(PROACTIVE_PHONE_TOOL_NAMES)
    if context.echo_computer_online:
        names.extend(ECHO_COMPUTER_TOOL_NAMES)
    return tuple(dict.fromkeys(names))
