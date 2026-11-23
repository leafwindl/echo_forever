"""Echo 的主动动作目录：念头只能声明这里注册过的动作。

新增动作只改这里：念头提示、工具面和执行提示都从同一份定义派生。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    label: str
    instruction: str
    tool_scope: tuple[str, ...] | None = None


ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        kind="bili",
        label="bili:想看看——想自己去B站刷推荐流，看看有没有有趣的视频",
        instruction=(
            "去B站刷推荐流，挑最多2个值得的视频用 bili_share 发给用户；"
            "看完记得写一句你看了什么、什么感觉。"
        ),
        tool_scope=("bili_browse", "bili_share", "emit_chat_beats", "send_sticker"),
    ),
    ActionSpec(
        kind="music",
        label="music:歌曲或歌手——想放一首合适的歌",
        instruction="放一首符合当下语境的歌，放完用一句话说说为什么选它。",
        tool_scope=("desktop_music_search_play", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="notepad",
        label="notepad:要留下的短句——想写一张便签",
        instruction="把想留的短句写进记事本，写完用一句话说明。",
        tool_scope=("desktop_notepad_write", "emit_chat_beats"),
    ),
    ActionSpec(
        kind="dsh",
        label="dsh:明确的任务——用户之前提过、适合交给电脑执行的任务",
        instruction="把用户之前提过的任务交给电脑执行，完成后如实汇报结果。",
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


__all__ = [
    "ACTION_SPECS",
    "ActionSpec",
    "get_action_spec",
    "parse_action_kind",
]
