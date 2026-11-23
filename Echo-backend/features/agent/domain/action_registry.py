"""Echo 的主动动作目录：念头可以声明想做什么，系统按这里路由。

新增动作只改这里：念头提示、工具面和执行提示都从同一份定义派生。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    label: str
    instruction: str
    keywords: tuple[str, ...] = ()
    tool_scope: tuple[str, ...] | None = None


ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        kind="bili",
        label="bili:想看看——想自己去B站刷推荐流，看看有没有有趣的视频",
        instruction=(
            "去B站刷推荐流，挑最多2个值得的视频用 bili_share 发给用户；"
            "看完记得写一句你看了什么、什么感觉。"
        ),
        keywords=("B站", "b站", "刷视频", "推荐流", "刷刷"),
        tool_scope=("bili_browse", "bili_share", "emit_chat_beats", "send_sticker"),
    ),
    ActionSpec(
        kind="look",
        label="look:想看看你的屏幕——想看看用户在电脑上做什么",
        instruction="看一眼用户电脑上的画面，然后用一句话说说你看到了什么。",
        keywords=("屏幕", "电脑上"),
        tool_scope=("desktop_look", "desktop_screenshot", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="phone_look",
        label="phone_look:想看看你的手机——想看看用户在手机上做什么",
        instruction="看一眼用户手机上的画面，然后用一句话说说你看到了什么。",
        keywords=("手机", "摄像头"),
        tool_scope=("phone_observe", "phone_screenshot", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="music",
        label="music:歌曲或歌手——想放一首合适的歌",
        instruction="放一首符合当下语境的歌，放完用一句话说说为什么选它。",
        keywords=("放歌", "听歌", "音乐"),
        tool_scope=("desktop_music_search_play", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="notepad",
        label="notepad:要留下的短句——想写一张便签",
        instruction="把想留的短句写进记事本，写完用一句话说明。",
        keywords=("便签", "记下来", "写下"),
        tool_scope=("desktop_notepad_write", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="dsh",
        label="dsh:明确的任务——用户之前提过、适合交给电脑执行的任务",
        instruction="把用户之前提过的任务交给电脑执行，完成后如实汇报结果。",
        keywords=("电脑执行", "跑个任务"),
        tool_scope=("desktop_dsh_task", "emit_chat_beats"),
    ),
)

_BY_KIND = {spec.kind: spec for spec in ACTION_SPECS}


def get_action_spec(kind: str) -> ActionSpec | None:
    return _BY_KIND.get(kind.strip().lower())


def parse_action_kind(action_intent: str) -> str:
    clean = action_intent.strip()
    if ":" not in clean:
        return ""
    return clean.split(":", 1)[0].strip().lower()


def route_action_request(request: str) -> str:
    """把自然语言能力请求路由成已注册的 action_intent；匹配不到返回空。

    匹配不到说明这是当前没有的能力，调用方应记录能力缺口，而不是硬做。
    """
    clean = " ".join(request.split()).strip()
    if not clean:
        return ""
    kind = parse_action_kind(clean)
    if kind and kind in _BY_KIND:
        return clean
    for spec in ACTION_SPECS:
        if any(keyword in clean for keyword in spec.keywords):
            return f"{spec.kind}:{clean[:160]}"
    return ""


__all__ = [
    "ACTION_SPECS",
    "ActionSpec",
    "get_action_spec",
    "parse_action_kind",
    "route_action_request",
]
