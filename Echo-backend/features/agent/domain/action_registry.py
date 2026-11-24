"""Echo 的主动动作目录：按「接触用户的程度」分为 L0/L1/L2。

- L0：自己做，不接触用户，只写内部历史。
- L1：轻微打扰，会接触用户，发微信并受打扰预算限制。
- L2：请求回应，只发提议/询问，等用户同意后再执行。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    label: str
    instruction: str
    tier: int = 0
    keywords: tuple[str, ...] = ()
    tool_scope: tuple[str, ...] | None = None


ACTION_SPECS: tuple[ActionSpec, ...] = (
    # ---- L0：自己做，不接触用户 ----
    ActionSpec(
        kind="bili",
        tier=0,
        label="bili:想看看——自己刷B站，不分享",
        instruction="刷B站推荐流，挑值得的记下来；这一轮不要分享给用户。",
        keywords=("B站", "b站", "刷视频", "推荐流"),
        tool_scope=("bili_browse",),
    ),
    ActionSpec(
        kind="selfie",
        tier=0,
        label="selfie:看看自己的屏幕——看看自己电脑上在发生什么",
        instruction="看一眼自己电脑的屏幕，记录你看到了什么。",
        keywords=("自己的屏幕", "看看自己"),
        tool_scope=("computer_screenshot",),
    ),
    ActionSpec(
        kind="reflect",
        tier=0,
        label="reflect:整理/准备——整理记忆或准备话题",
        instruction="回顾最近的聊天和记忆，写一条简短的内部整理或话题准备。",
        keywords=("整理", "回忆", "准备话题"),
        tool_scope=(),
    ),
    # ---- L1：轻微打扰，会接触用户 ----
    ActionSpec(
        kind="share",
        tier=1,
        label="share:分享——从最近刷到的B站候选里挑1-2个发给用户",
        instruction=(
            "从最近的B站候选里挑1-2个，用 bili_share 发给用户；话术自然，别念标题。"
        ),
        keywords=("分享", "发我"),
        tool_scope=("bili_share", "emit_chat_beats", "send_sticker"),
    ),
    ActionSpec(
        kind="look",
        tier=1,
        label="look:看看你的屏幕——看用户在电脑上做什么",
        instruction="看一眼用户电脑屏幕，用一句话说说你看到了什么。",
        keywords=("屏幕", "电脑上"),
        tool_scope=("desktop_look", "desktop_screenshot"),
    ),
    ActionSpec(
        kind="phone_look",
        tier=1,
        label="phone_look:看看你的手机——看用户在手机上做什么",
        instruction="看一眼用户手机，用一句话说说你看到了什么。",
        keywords=("手机", "摄像头"),
        tool_scope=("phone_observe", "phone_screenshot", "phone_notifications"),
    ),
    ActionSpec(
        kind="music",
        tier=1,
        label="music:放歌——在用户电脑放一首合适的歌",
        instruction="放一首符合语境的歌，放完用一句话说说为什么选它。",
        keywords=("放歌", "听歌", "音乐"),
        tool_scope=("desktop_music_search_play",),
    ),
    ActionSpec(
        kind="notepad",
        tier=1,
        label="notepad:写便签——在用户电脑写一张便签",
        instruction="写一张便签，写完用一句话说明。",
        keywords=("便签", "写下"),
        tool_scope=("desktop_notepad_write",),
    ),
    ActionSpec(
        kind="sticker",
        tier=1,
        label="sticker:发个表情——按语境主动发一个表情包",
        instruction="按当前语境挑一个合适的表情包发给用户。",
        keywords=("表情", "表情包"),
        tool_scope=("send_sticker",),
    ),
    # ---- L2：请求回应 ----
    ActionSpec(
        kind="propose",
        tier=2,
        label="propose:提议——问用户要不要一起做点什么",
        instruction="发一条自然的提议或询问，等用户回应；不要直接执行工具。",
        keywords=("要不要", "提议", "一起"),
        tool_scope=(),
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


def actions_for_tier(tier: int) -> tuple[str, ...]:
    return tuple(spec.kind for spec in ACTION_SPECS if spec.tier == tier)


def route_action_request(request: str) -> str:
    """把自然语言能力请求路由成已注册的 action_intent；匹配不到返回空。"""
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
    "actions_for_tier",
    "get_action_spec",
    "parse_action_kind",
    "route_action_request",
]
